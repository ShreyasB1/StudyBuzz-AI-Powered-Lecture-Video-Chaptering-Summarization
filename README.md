# StudyBuzz

**AI-Powered Lecture Video Chaptering & Summarization**

StudyBuzz transforms hour-long lecture recordings into navigable, summarized content. Upload a video, get chapters and summaries—automatically.

---

## Features

- **Automatic Transcription** — Whisper-powered speech-to-text with precise timestamps
- **Smart Chapters** — AI detects topic transitions and generates meaningful segment markers
- **AI Summaries** — Each chapter receives a concise 1-2 paragraph summary
- **Interactive Player** — Click any chapter to jump directly to that section
- **Supports Multiple Formats** — MP4, MKV, MOV, AVI, WEBM, MPEG (up to 2GB)

---

## Architecture
```
┌─────────────────────────────────────────────────────┐
│         FRONTEND (React + Material-UI)              │
│  - Video upload interface                           │
│  - Processing status display                        │
│  - Video player with chapters                       │
│  - Summary panels                                   │
└─────────────────────────────────────────────────────┘
                        ↕ HTTP/REST API
┌─────────────────────────────────────────────────────┐
│          BACKEND (Flask + Python)                   │
│  - REST API endpoints (/api/*)                      │
│  - File management (uploads/output)                 │
│  - Job orchestration                                │
│  - Static file serving                              │
└─────────────────────────────────────────────────────┘
                        ↕ Subprocess calls
┌─────────────────────────────────────────────────────┐
│      PROCESSING PIPELINE (timeStampGen.py)          │
│  - FFmpeg (audio/video manipulation)                │
│  - Whisper-CLI (speech transcription)               │
│  - Local LLM API (timestamp + summary generation)   │
└─────────────────────────────────────────────────────┘
```

---

## Pipeline Stages

| Stage | Tool | Input | Output |
|-------|------|-------|--------|
| 1. Audio Extraction | FFmpeg | `video.mp4` | `video.wav` |
| 2. Speech Transcription | Whisper.cpp | `video.wav` | `video.wav.vtt` |
| 3. Chapter Generation | Qwen3-VL | transcript | `video_timestamps.txt` |
| 4. Video Segmentation | FFmpeg | video + timestamps | `clip_01.mp4`, `clip_02.mp4`... |
| 5. Transcript Segmentation | Python | VTT + timestamps | `chapter_01.vtt`, `chapter_02.vtt`... |
| 6. Chapter Summarization | Qwen3-VL (multimodal) | clips + transcripts | `video_summary.json` |

---

## Prerequisites

### System Dependencies

- **Python 3.10+**
- **Node.js 18+** and npm
- **FFmpeg** — must be on system PATH
- **Whisper.cpp** — compiled with GPU support (`whisper-cli` binary on PATH)
- **Podman** — for running vLLM container

### Models

- **Whisper**: `ggml-large-v3-turbo.bin`
- **LLM**: `Qwen/Qwen3-VL-235B-A22B-Thinking-FP8` (served via vLLM)

---

## Installation

### 1. Clone the Repository
```bash
git clone https://github.gatech.edu/OLIVES-VIP-VP4-AIMN/M-SB-TUT-Stud-1.git
```

### 2. Backend Setup
```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Frontend Setup
```bash
cd frontend/video-summarizer-ui
npm install
npm run build
cd ../..
```

### 4. Start vLLM Server

Run from the `output` directory (create if it doesn't exist). Ensure a `video/` subdirectory exists for clip storage.
```bash
mkdir -p output/video
cd output

podman run --device nvidia.com/gpu=all \
  -v ~/studybuzz/huggingface:/root/.cache/huggingface \
  -v $(pwd)/video:/root/video \
  -p 8000:8000 \
  --ipc=host \
  docker.io/vllm/vllm-openai:latest \
  --model Qwen/Qwen3-VL-235B-A22B-Thinking-FP8 \
  --served-model-name Qwen3-VL \
  --enable-expert-parallel \
  --swap-space 16 \
  --max-num-seqs 512 \
  --gpu-memory-utilization 0.9 \
  --tensor-parallel-size 8 \
  --allowed-local-media-path /root/video \
  --trust-remote-code \
  --host 0.0.0.0 \
  --port 8000
```

> **Note**: vLLM takes ~20 minutes to load the model. Wait for the server to be ready before processing videos.

### 5. Start the Application
```bash
python app.py
```

The application will be available at `https://ondemand-ice.pace.gatech.edu/node/{YourHostHere}/5000/`.

---

### Command Line (Pipeline Only)
```bash
python timeStampGen.py <video_file> -o <output_directory>

# Example
python timeStampGen.py lecture.mp4 -o output
```

#### CLI Options
```
usage: timeStampGen.py [-h] [-d INPUT_DIR] [-o OUTPUT_DIR] [input_file]

positional arguments:
  input_file            Path to video file

optional arguments:
  -h, --help            Show help message
  -d, --input-dir       Process all videos in directory
  -o, --output-dir      Output directory (default: ./output)
```

---

## Project Structure
```
studybuzz/
├── app.py                      # Flask backend server
├── timeStampGen.py             # Main processing pipeline
├── requirements.txt            # Python dependencies
│
├── frontend/
│   └── video-summarizer-ui/
│       ├── src/
│       │   ├── App.js          # Main React component
│       │   ├── api.js          # API client
│       │   └── components/
│       │       ├── VideoUploader.js
│       │       ├── ProcessingStatus.js
│       │       ├── VideoPlayer.js
│       │       ├── ChapterMarkers.js
│       │       └── SummaryPanel.js
│       ├── package.json
│       └── build/              # Production build (generated)
│
├── uploads/                    # Uploaded video files
│
└── output/                     # Generated artifacts
```

## Troubleshooting

### Chapters are inaccurate

- Ensure vLLM server is fully loaded before processing
- Check that video clips are being written to the mounted `video/` directory
- Verify the `--allowed-local-media-path` flag is set correctly


## Acknowledgments

- [Whisper.cpp](https://github.com/ggerganov/whisper.cpp)
- [vLLM](https://github.com/vllm-project/vllm)
- Georgia Tech AI Makerspace (https://coe.gatech.edu/academics/ai-for-engineering/ai-makerspace)