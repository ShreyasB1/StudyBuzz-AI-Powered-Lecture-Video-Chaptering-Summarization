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

## Deploying on PACE Sandbox (Open OnDemand)

StudyBuzz can be deployed as an interactive app on Georgia Tech's PACE Sandbox through Open OnDemand. This containerizes the application and makes it launchable from a web dashboard with automatic GPU allocation.

### Prerequisites

- SSH access to PACE (`login-ice.pace.gatech.edu`)
- Podman available on the cluster (pre-installed on PACE)
- Load your model in the shared library (e.g., `/storage/ice-shared/vip-vp4/huggingface`)
- Load your Whisper model or whatever speech-to-text model shared storage (e.g., `/storage/ice-shared/vip-vp4/whisper`)

### Step 1: Clone into the OnDemand dev directory

Open OnDemand discovers apps placed in `~/ondemand/dev/` in your PACE file directory. Clone or copy the repository there:

```bash
ssh <your-gt-username>@login-ice.pace.gatech.edu

cd <insert-path-to-your-dev-folder>
git clone https://github.gatech.edu/OLIVES-VIP-VP4-AIMN/M-SB-TUT-Stud-1.git 
```

### Step 2: Pre-build container images

From inside the app directory (you should be in `/ondemand/dev/SB-V-1a`), run the install script to build the StudyBuzz Docker image and pull the vLLM image. This caches the images so job startup is faster. `sed -i 's/\r$//' install.sh` is an optional command but is needed for files that are edited on Windows that have CRLF line endings that break shell scripts on Linux machines. The `install.sh` script should be able to hanlde this automatically but you must fix `install.sh` itself using the command.

```bash
sed -i 's/\r$//' install.sh

bash install.sh
```

> **Note:** The first build takes several minutes (npm install + Python deps). Subsequent builds use cached layers and are much faster.

### Step 3: Launch from Open OnDemand

1. Go to **https://ondemand-ice.pace.gatech.edu** 
2. Navigate to **Develop** (top menu) and find **StudyBuzz** or whatever you name it (apps in `~/ondemand/dev/` appear here)
3. Fill out the launch form:
   - **HuggingFace Model Cache Path** — directory containing the model weights (will be empty for now since not using Qwen anymore)
   - **Whisper Tools Path** — directory containing `whisper-cli` and `ggml-large-v3-turbo.bin` (not currently there FYI!)
   - **Node Type** — select **H200 HGX** (recommended) 
   - **GPUs** — set to **8** 
   - **Cores** — 8 recommended
   - **Memory Per Core** — 16 GB recommended
   - Set your desired **job duration**
4. Click **Launch**

### Step 4: Connect

Once the SLURM job starts and containers are ready, a **Connect to StudyBuzz** button appears. Click it to open the web UI.

> **Startup time:** vLLM takes potentially up to 20 minutes to load the models. The web interface is accessible immediately, but video processing will not work until the model finishes loading.

### How it works

```
Open OnDemand Dashboard
    │
    ▼ (SLURM job submission)
Compute Node (H200 HGX, 8 GPUs)
    │
    ├── Podman Pod (shared localhost network)
    │     ├── studybuzz-app container    ← Flask + React + FFmpeg (port 5000)
    │     └── vllm container            ← Qwen3-VL-235B-FP8 (port 8000)
    │
    ▼
User accesses: https://ondemand-ice.pace.gatech.edu/node/<host>/<port>/
```

The deployment is managed by these files:

| File | Purpose |
|------|---------|
| `Dockerfile` | Builds the StudyBuzz app image (React build + Python/Flask + FFmpeg) |
| `manifest.yml` | Registers the app with Open OnDemand |
| `form.yml.erb` | Defines the launch form (GPU count, paths, resources) |
| `submit.yml.erb` | Configures SLURM job parameters |
| `view.html.erb` | Renders the "Connect" button in the dashboard |
| `template/before.sh.erb` | Allocates ports and exports environment variables |
| `template/script.sh.erb` | Main script: creates Podman pod, starts vLLM and app containers |
| `template/after.sh` | Waits for the app to become responsive |
| `template/clean.sh` | Cleans up containers when the job ends |
| `Makefile` | Helper targets for manual container management |
| `install.sh` | One-time image pre-build script |

### Updating the deployed app

After making code changes, push to GitHub and pull on PACE:

```bash
cd ~/ondemand/dev/studybuzz
git pull
sed -i 's/\r$//' install.sh
bash install.sh   # rebuild the Docker image with your changes
```

Then launch a new session from the OnDemand dashboard.

---

## Troubleshooting

### Checking logs

Each session writes logs to the output directory shown in the OnDemand session card. To check what happened during a session:

1. In the OnDemand session list, find the session's output directory path
2. SSH in and read `output.log` in that directory
3. Or click the session's folder icon in the OnDemand dashboard to browse logs in the file manager

### Chapters are inaccurate

- Ensure vLLM server is fully loaded before processing
- Check that video clips are being written to the mounted `video/` directory
- Verify the `--allowed-local-media-path` flag is set correctly

### Podman build fails with `setgroups` or `seteuid` errors

This happens on PACE because rootless Podman does not have subuid/subgid ranges configured. The Dockerfile works around this by passing `-o APT::Sandbox::User=root` to apt-get. If you add new Dockerfiles, include the same flag in `apt-get` commands.

### `debconf: unable to initialize frontend` warnings during build

These are harmless. They appear because apt-get runs non-interactively inside the Docker build and can't find a terminal for configuration dialogs. Packages still install correctly.


### `npm ci` fails with "package-lock.json out of sync"

The Dockerfile uses `npm install` instead of `npm ci` to handle lock file mismatches. If you update `package.json`, run `npm install` locally to regenerate the lock file.

### vLLM container exits immediately

- Check logs: `podman logs vllm-<SLURM_JOB_ID>`
- Verify the HuggingFace cache path contains the model weights
- Ensure you requested enough GPUs (8 for tensor-parallel-size 8)


## Acknowledgments

- [Whisper.cpp](https://github.com/ggerganov/whisper.cpp)
- [vLLM](https://github.com/vllm-project/vllm)
- Georgia Tech AI Makerspace (https://coe.gatech.edu/academics/ai-for-engineering/ai-makerspace)
- Open OnDemand (https://osc.github.io/ood-documentation/latest/)