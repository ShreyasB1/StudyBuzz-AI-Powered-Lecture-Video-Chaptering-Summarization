# StudyBuzz (M-SB-TUT-Stud-1)

**AI-Powered Lecture Video Chaptering & Summarization**

StudyBuzz transforms hour-long lecture recordings into navigable, summarized content. Upload a video, get chapters and summaries — automatically.

---

## Features

- **Automatic Transcription** — Whisper-powered speech-to-text via vLLM API with precise timestamps
- **Smart Chapters** — Mistral-Large-3 detects topic transitions and generates meaningful segment markers
- **Scene Detection** — FFmpeg extracts key frames at scene changes for visual context
- **AI Summaries** — Each chapter receives a concise summary using multimodal LLM analysis (text + frames)
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
│  - Static file serving                              │
└─────────────────────────────────────────────────────┘
                        ↕ Subprocess / HTTP calls
┌─────────────────────────────────────────────────────┐
│      PROCESSING PIPELINE (timeStampGen.py)          │
│  - FFmpeg (audio extraction, scene detection)       │
│  - Whisper vLLM API (speech transcription, :8001)   │
│  - Mistral-Large-3 vLLM API (chapters + summaries,  │
│    :8000)                                           │
└─────────────────────────────────────────────────────┘
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
  docker.io/vllm/vllm-openai:qwen3_5-x86_64-cu129 \
  -c "pip install librosa soundfile && python3 -m vllm.entrypoints.openai.api_server \
    --model openai/whisper-large-v3 \
    --served-model-name whisper \
    --dtype bfloat16 \
    --max-model-len 448 \
    --tensor-parallel-size 1 \
    --swap-space 16 \
    --gpu-memory-utilization 0.075 \
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

### 3. Start the Database (pgvector)

```bash
podman run -d \
  --name pgvector_local \
  --userns=keep-id \
  --net=host \
  -e POSTGRES_PASSWORD=mysecret \
  -e PGDATA=/var/lib/postgresql/data/pgdata \
  -e PGPORT=5432 \
  -v ./my_pgdata:/var/lib/postgresql/data \
  pgvector/pgvector:pg18-trixie
```

### 4. Start the Application

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

## Deploying on PACE Sandbox (Open OnDemand)

StudyBuzz can be deployed as an interactive app on Georgia Tech's PACE Sandbox through Open OnDemand. This containerizes the application and makes it launchable from a web dashboard with automatic GPU allocation.

### Prerequisites

- SSH access to PACE (`login-ice.pace.gatech.edu`)
- Podman available on the cluster (pre-installed on PACE)
- HuggingFace token with access to Mistral-Large-3 (gated model)
- Model weights cached at a shared path (e.g., `/storage/ice-shared/vip-vp4/Spring2026/SB-V-1a/huggingface`)

### Step 1: Clone into the OnDemand dev directory

Open OnDemand discovers apps placed in `~/ondemand/dev/` in your PACE file directory. Clone or copy the repository there:

```bash
ssh <your-gt-username>@login-ice.pace.gatech.edu

cd ~/ondemand/dev
git clone https://github.gatech.edu/OLIVES-VIP-VP4-AIMN/M-SB-TUT-Stud-1.git SB-V-1a
cd SB-V-1a
```

### Step 2: Pre-build container images

From inside the app directory, run the install script to build the StudyBuzz Docker image and pull both vLLM images. Fix CRLF line endings first if the code was edited on Windows.

```bash
sed -i 's/\r$//' install.sh

bash install.sh
```

This will:
1. Fix CRLF line endings on all deployment scripts
2. Build the StudyBuzz app image (Python + FFmpeg)
3. Pull the Mistral vLLM image (`vllm-openai:qwen3_5-x86_64-cu129`)
4. Pull the Whisper vLLM image (`vllm-openai:v0.14.0`)

### Step 3: Launch from Open OnDemand

1. Go to **https://ondemand-ice.pace.gatech.edu**
2. Navigate to **Develop** (top menu) and find **StudyBuzz**
3. Fill out the launch form:
   - **HuggingFace Model Cache Path** — directory containing the model weights (default: `/storage/ice-shared/vip-vp4/Spring2026/SB-V-1a/huggingface`)
   - **HuggingFace Token** — your full HF token including the `hf_` prefix, needed for gated models
   - **Node Type** — select **H200 HGX** (recommended)
   - **GPUs** — set to **8**
   - **Cores** — 8 recommended
   - **Memory Per Core** — 16 GB recommended
   - Set your desired **job duration**
4. Click **Launch**

### Step 4: Connect

Once the SLURM job starts and containers are ready, a **Connect to StudyBuzz** button appears. Click it to open the web UI.

> **Startup time:** The web interface is accessible within minutes. Mistral takes ~20 minutes to load, Whisper takes ~2 minutes. Video processing will not work until both models finish loading. Use the **Service Health** check button in the UI to monitor readiness.

### How it works

```
Open OnDemand Dashboard
    │
    ▼ (SLURM job submission)
Compute Node (H200 HGX, 8 GPUs)
    │
    ├── Podman Pod (shared localhost network)
    │     ├── studybuzz-app container     ← Flask + FFmpeg (port 5000)
    │     ├── mistral-vllm container      ← Mistral-Large-3-675B (port 8000, 90% VRAM)
    │     └── whisper-vllm container      ← Whisper-large-v3 (port 8001, 9% VRAM)
    │
    ▼
User accesses: https://ondemand-ice.pace.gatech.edu/node/<host>/<port>/
```

### Updating the deployed app

After making code changes, push to GitHub and pull on PACE:

```bash
cd ~/ondemand/dev/SB-V-1a
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
