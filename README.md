# StudyBuzz (M-SB-TUT-Stud-1)

**AI-Powered Lecture Video Chaptering & Summarization**

StudyBuzz transforms hour-long lecture recordings into navigable, summarized content. Upload a video, get chapters and summaries — automatically.

---

## Features

- **Automatic Transcription** — Whisper-powered speech-to-text via vLLM API with precise timestamps
- **Smart Chapters** — Mistral-Large-3 detects topic transitions and generates meaningful segment markers
- **Scene Detection** — FFmpeg extracts key frames at scene changes for visual context
- **AI Summaries** — Each chapter receives a concise summary using multimodal LLM analysis (text + frames)
- **Database Tracking** — PostgreSQL with pgvector stores video metadata and chapter embeddings for duplicate detection and similarity search
- **Supports Multiple Formats** — MP4, MKV, MOV, AVI, WEBM, MPEG

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│         FRONTEND (Minimal HTML served by Flask)     │
│  - Video upload interface                           │
│  - Processing status display                        │
│  - Results viewer (chapters, summaries, transcript) │
│  - Service health check                             │
└─────────────────────────────────────────────────────┘
                        ↕ HTTP/REST API
┌─────────────────────────────────────────────────────┐
│          BACKEND (Flask + Python)                   │
│  - REST API endpoints (/api/*)                      │
│  - File management (uploads/output)                 │
│  - Job orchestration (background threads)           │
│  - Database integration (video tracking)            │
│  - Static file serving                              │
└─────────────────────────────────────────────────────┘
       ↕ Subprocess / HTTP calls              ↕ SQL
┌──────────────────────────────┐    ┌──────────────────┐
│   PROCESSING PIPELINE        │    │   PostgreSQL     │
│   (timeStampGen.py)          │    │   + pgvector     │
│  - FFmpeg                    │    │  - Video records │
│  - Whisper vLLM (:8001)      │    │  - Embeddings    │
│  - Mistral-Large-3 (:8000)   │    │  - Deduplication │
└──────────────────────────────┘    └──────────────────┘
```

---

## Pipeline Stages

| Stage | Tool | Input | Output |
|-------|------|-------|--------|
| 1. Audio Extraction | FFmpeg | `video.mp4` | `video.mp3` |
| 2. Speech Transcription | Whisper (vLLM API, port 8001) | `video.mp3` | `video.mp3.vtt` |
| 3. Chapter Generation | Mistral-Large-3 (vLLM API, port 8000) | transcript | `video_timestamps.txt` |
| 4. Video Segmentation | FFmpeg | video + timestamps | `clip_01.mp4`, `clip_02.mp4`... |
| 5. Transcript Segmentation | Python | VTT + timestamps | `chapter_01.vtt`, `chapter_02.vtt`... |
| 6. Scene Frame Extraction | FFmpeg | clips | base64 PNG frames |
| 7. Chapter Summarization | Mistral-Large-3 (multimodal) | clips + transcripts + frames | `video_summary.json` |

---

## Prerequisites

### System Dependencies

- **Python 3.10+**
- **FFmpeg** — must be on system PATH
- **Podman** — for running vLLM containers

### Models (served via vLLM)

- **Mistral-Large-3**: `mistralai/Mistral-Large-3-675B-Instruct-2512` (port 8000, 8 GPUs)
- **Whisper**: `openai/whisper-large-v3` (port 8001, 1 GPU, 9% VRAM)

---

## VLLM Setup

VLLM is used for running the large language model and the transcription model. We use podman to run the VLLM servers to avoid dependency issues.

### Mistral-Large-3 Server

```bash
podman run --device nvidia.com/gpu=all \
  --security-opt=label=disable \
  --ipc=host \
  -p 8000:8000 \
  -v /storage/ice-shared/vip-vp4/Spring2026/SB-V-1a/huggingface:/root/.cache/huggingface \
  --env "HUGGING_FACE_HUB_TOKEN=<YOUR_HF_TOKEN>" \
  --env "NCCL_DEBUG=INFO" \
  --env "OMP_NUM_THREADS=16" \
  docker.io/vllm/vllm-openai:qwen3_5-x86_64-cu129 \
  --model mistralai/Mistral-Large-3-675B-Instruct-2512 \
  --served-model-name mistral-large \
  --tensor-parallel-size 8 \
  --gpu-memory-utilization 0.90 \
  --max-model-len 196608 \
  --limit-mm-per-prompt '{"image": 32}' \
  --max-num-batched-tokens 8192 \
  --enable-chunked-prefill \
  --max-num-seqs 2 \
  --load-format mistral \
  --tokenizer-mode mistral \
  --config-format mistral \
  --enable-auto-tool-choice \
  --tool-call-parser mistral
```

The Mistral VLLM server will be accessible at `http://localhost:8000`.

> **Note**: Mistral takes ~20 minutes to load the model.

### Whisper Server

```bash
podman run --device nvidia.com/gpu=all \
  --entrypoint /bin/bash \
  --security-opt=label=disable \
  -v /storage/ice-shared/vip-vp4/Spring2026/SB-V-1a/huggingface:/root/.cache/huggingface \
  -p 8001:8000 \
  --ipc=host \
  --env "HUGGING_FACE_HUB_TOKEN=<YOUR_HF_TOKEN>" \
  -e VLLM_USE_DEEP_GEMM=0 \
  docker.io/vllm/vllm-openai:v0.14.0 \
  -c "pip install librosa soundfile && python3 -m vllm.entrypoints.openai.api_server \
    --model openai/whisper-large-v3 \
    --served-model-name whisper \
    --dtype bfloat16 \
    --max-model-len 448 \
    --tensor-parallel-size 1 \
    --swap-space 16 \
    --gpu-memory-utilization 0.09 \
    --trust-remote-code \
    --host 0.0.0.0 \
    --port 8000"
```

The Whisper VLLM server will be accessible at `http://localhost:8001`.

> **Note**: Whisper loads in ~2 minutes.

The commands must be run in the output directory (create it if it does not exist) where the `timeStampGen.py` script will output the intermediate files. There must also be a `video/` directory in the output directory where the input video is stored.

---

## Installation

### 1. Clone the Repository

```bash
git clone https://github.gatech.edu/OLIVES-VIP-VP4-AIMN/M-SB-TUT-Stud-1.git
```

### 2. Python Dependencies

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -r requirements_backend.txt
```

### 3. Start the Application

```bash
python app.py
```

The application will be available at `http://localhost:5000`.

---

## Video Summary Pipeline (CLI)

The main code for the video summary pipeline is in `timeStampGen.py`. This script takes a video file as input and outputs a text summary of the video. It uses the VLLM server to run the Mistral model for video understanding. The VLLM server must be running before executing this script.

Run:
```bash
timeStampGen.py --help
```
to see the usage of the script. The main arguments are:

```
usage: timeStampGen.py [-h] [-d INPUT_DIR] [-o OUTPUT_DIR] [input_file]
```

A sample command to run the script is as follows:
```bash
python timeStampGen.py lecture.mp4
```

---

## Project Structure

```
SB-V-1a/
├── app.py                      # Flask backend server
├── timeStampGen.py             # Main processing pipeline
├── vllm_to_vtt.py              # VTT conversion utility
├── init_db.py                  # PostgreSQL database initialization
├── vip_db                      # SQL schema (pgvector)
├── requirements.txt            # Pipeline dependencies (httpx, openai)
├── requirements_backend.txt    # Backend dependencies (Flask, psycopg)
├── static/
│   └── index.html              # Minimal test frontend
├── Dockerfile                  # App container image definition
├── .dockerignore               # Docker build exclusions
├── manifest.yml                # Open OnDemand app registration
├── form.yml.erb                # OnDemand launch form
├── submit.yml.erb              # SLURM job parameters
├── view.html.erb               # OnDemand connect button
├── template/
│   ├── before.sh.erb           # Port allocation, env setup
│   ├── script.sh.erb           # Main deployment script (3 containers)
│   ├── after.sh                # Wait for app readiness
│   └── clean.sh                # Container cleanup
├── Makefile                    # Manual container management
├── install.sh                  # One-time image pre-build
├── uploads/                    # Uploaded video files
└── output/                     # Generated artifacts
```

---

## Database

StudyBuzz uses PostgreSQL with the pgvector extension to track processed videos and store chapter embeddings.

### Database Schema

**`lecture_videos` table:**
- Stores metadata for each processed video
- Uses SHA256 hash for deduplication
- Tracks processing status

**`chapter_embeddings` table:**
- Stores vector embeddings for chapters (1536 dimensions)
- Enables semantic similarity search across chapters
- Uses IVFFlat index for fast approximate nearest neighbor queries

### Database Endpoints

**Check database health:**
```bash
curl http://localhost:5000/api/health
```

**List all processed videos:**
```bash
curl http://localhost:5000/api/database/videos
```

### Inspecting the Database

**On your local machine (with `make run-db`):**
```bash
# Using psql
psql -h localhost -p 5432 -U postgres -d vip_db

# List all videos
SELECT video_name, done_processing, video_date FROM lecture_videos;

# Count chapter embeddings
SELECT COUNT(*) FROM chapter_embeddings;
```

**On PACE (during an active session):**
```bash
# SSH into the compute node
# Then connect to the PostgreSQL container
podman exec -it studybuzz-postgres-<SLURM_JOB_ID> psql -U postgres -d vip_db

# Run SQL queries
\dt                    # List tables
\d lecture_videos      # Describe table schema
SELECT * FROM lecture_videos LIMIT 5;
```

### Database Features

1. **Duplicate Detection** — Videos are hashed on upload; previously processed videos skip re-processing
2. **Processing History** — All videos and their processing status are permanently stored
3. **Future: Semantic Search** — Chapter embeddings enable finding similar content across videos

---

## Troubleshooting

### Checking logs

Each session writes logs to the output directory shown in the OnDemand session card. To check what happened during a session:

1. In the OnDemand session list, find the session's output directory path
2. SSH in and read `output.log` in that directory
3. Or click the session's folder icon in the OnDemand dashboard to browse logs in the file manager

### Chapters are inaccurate

- Ensure Mistral vLLM server is fully loaded before processing (check health endpoint)
- Check that video clips are being written to the mounted `video/` directory
- Verify the `--allowed-local-media-path` flag is set correctly

### Podman build fails with `setgroups` or `seteuid` errors

This happens on PACE because rootless Podman does not have subuid/subgid ranges configured. The Dockerfile works around this by passing `-o APT::Sandbox::User=root` to apt-get. If you add new Dockerfiles, include the same flag in `apt-get` commands.

### `debconf: unable to initialize frontend` warnings during build

These are harmless. They appear because apt-get runs non-interactively inside the Docker build and can't find a terminal for configuration dialogs. Packages still install correctly.

### vLLM container exits immediately

- Check logs: `podman logs mistral-vllm-<SLURM_JOB_ID>` or `podman logs whisper-vllm-<SLURM_JOB_ID>`
- Verify the HuggingFace cache path contains the model weights
- Ensure you requested enough GPUs (8 for tensor-parallel-size 8)
- Check that the HF token is valid and has access to the gated model

### Whisper transcription fails

- Verify Whisper is healthy: `curl http://localhost:8001/health`
- Check that the audio file was converted to MP3 successfully
- Review Whisper container logs for errors

---

## Acknowledgments

- [Mistral AI](https://mistral.ai/) — Mistral-Large-3
- [OpenAI Whisper](https://github.com/openai/whisper)
- [vLLM](https://github.com/vllm-project/vllm)
- Georgia Tech AI Makerspace (https://coe.gatech.edu/academics/ai-for-engineering/ai-makerspace)
- Open OnDemand (https://osc.github.io/ood-documentation/latest/)
