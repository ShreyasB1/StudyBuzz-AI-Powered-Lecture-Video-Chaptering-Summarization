# StudyBuzz (M-SB-TUT-Stud-1)

**AI-Powered Lecture Video Chaptering & Summarization**

StudyBuzz transforms hour-long lecture recordings into navigable, summarized content. Upload a video, get chapters and summaries — automatically.

---

## Features

- **Automatic Transcription** — Whisper-powered speech-to-text via vLLM API with precise timestamps
- **Smart Chapters** — Mistral-Large-3 detects topic transitions and generates meaningful segment markers
- **Scene Detection** — FFmpeg extracts key frames at scene changes for visual context
- **AI Summaries** — Each chapter receives a concise summary using multimodal LLM analysis (text + frames)
- **Semantic Search** — Nemotron-8B text embeddings powered by Postgres pgvector for advanced chapter querying
- **Supports Multiple Formats** — MP4, MKV, MOV, AVI, WEBM, FLV, M4V, MPEG

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
│  - PostgreSQL Database connection (pgvector)        │
│  - Static file serving                              │
└─────────────────────────────────────────────────────┘
                        ↕ Subprocess / HTTP calls
┌─────────────────────────────────────────────────────┐
│      PROCESSING PIPELINE (timeStampGen.py)          │
│  - FFmpeg (audio extraction, scene detection)       │
│  - Whisper vLLM API (speech transcription, :8001)   │
│  - Mistral-Large-3 vLLM API (chapters + summaries,  │
│    :8000)                                           │
│  - Nemotron-8B vLLM API (embeddings, :8002)         │
└─────────────────────────────────────────────────────┘
```

---

## Pipeline Stages

The pipeline processes each video through the following stages. Scene frame extraction (Stage A) runs **in parallel** with Stages 1-4 to reduce total processing time.

| Stage | Tool | Input | Output |
|-------|------|-------|--------|
| 0. Database Registration | PostgreSQL | video file | `lecture_videos` row (processing=false) |
| 1. Audio Extraction | FFmpeg | `video.mp4` | `audio.mp3` |
| 2. Speech Transcription | Whisper (vLLM API, port 8001) | `audio.mp3` | `full_transcript.vtt` |
| 3. Chapter Generation | Mistral-Large-3 (vLLM API, port 8000) | transcript | `timestamps.txt` |
| 4. Transcript Segmentation | Python | VTT + timestamps | `chapter_NN_Title/transcript.vtt` |
| A. Scene Frame Extraction *(parallel)* | FFmpeg | source video | base64 PNG frames (temp) |
| 5. Chapter Summarization | Mistral-Large-3 (multimodal, ≤10 workers) | transcripts + frames | `chapters_summary.json` + per-chapter `summary.json` |
| 6. Vector Embeddings | Nemotron-8B (vLLM API, port 8002) | transcript + summary | `chapter_embeddings` table |
| 7. Finalize | PostgreSQL | — | `lecture_videos.done_processing = true` |
| 8. Cleanup | local filesystem | temp files | deletes `audio.mp3` + `all_frames_temp/` |

> **Note:** If a video hash already exists in the database with `done_processing = TRUE`, the entire pipeline is skipped. Use `--force` to override. If only a transcript file exists (but processing is not marked complete), Stages 1-2 are skipped automatically.

---

## Prerequisites

### System Dependencies

- **Python 3.10+**
- **FFmpeg** — must be on system PATH
- **Podman** — for running vLLM containers

### Models (served via vLLM)

- **Mistral-Large-3**: `mistralai/Mistral-Large-3-675B-Instruct-2512` (port 8000, 8 GPUs)
- **Whisper**: `openai/whisper-large-v3` (port 8001, 1 GPU, ~7.5% VRAM)
- **Nemotron-Embed**: `nvidia/llama-embed-nemotron-8b` (port 8002, 4 GPUs, ~7% VRAM)

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
  --tool-call-parser mistral \
  --disable-custom-all-reduce
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

### Nemotron-8B Embedder Server

```bash
podman run --device nvidia.com/gpu=all \
  --security-opt=label=disable \
  --ipc=host \
  -p 8002:8002 \
  -v /storage/ice-shared/vip-vp4/Spring2026/SB-V-1a/huggingface:/root/.cache/huggingface \
  --env "HUGGING_FACE_HUB_TOKEN=<YOUR_HF_TOKEN>" \
  --env "CUDA_VISIBLE_DEVICES=4,5,6,7" \
  --env "VLLM_USE_V1=0" \
  docker.io/vllm/vllm-openai:qwen3_5-x86_64-cu129 \
  --model nvidia/llama-embed-nemotron-8b \
  --served-model-name nemotron \
  --tensor-parallel-size 4 \
  --gpu-memory-utilization 0.07 \
  --max-model-len 32768 \
  --trust-remote-code \
  --dtype bfloat16 \
  --enforce-eager \
  --disable-custom-all-reduce \
  --host 0.0.0.0 \
  --port 8002
```

The Nemotron Embedder VLLM server will be accessible at `http://localhost:8002`.

> **Note**: `CUDA_VISIBLE_DEVICES` may need adjustment depending on your GPU topology. The `--disable-custom-all-reduce` flag prevents NCCL IPC conflicts when multiple vLLM instances share the same GPUs.

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

- `requirements.txt` — pipeline dependencies (`httpx`, `openai`)
- `requirements_backend.txt` — backend server dependencies (`Flask`, `flask-cors`, `Werkzeug`, `psycopg[binary]`)

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

The database schema is auto-initialized by `init_db.py` on first run (runs inside the Docker container via `CMD`).

### 4. Environment Variables

Database connection can be customized via environment variables (defaults shown):

| Variable | Default | Description |
|---|---|---|
| `VIP_DB_NAME` | `vip_db` | PostgreSQL database name |
| `VIP_DB_USER` | `postgres` | Database user |
| `VIP_DB_PASSWORD` | `mysecret` | Database password |
| `VIP_DB_HOST` | `localhost` | Database host |
| `VIP_DB_PORT` | `5432` | Database port |

### 5. Start the Application

```bash
python app.py
```

The application will be available at `http://localhost:5000`.

---

## Makefile Targets

The `Makefile` provides convenient targets for container management using Podman:

| Target | Description |
|---|---|
| `make help` | Show all available targets |
| `make build-app` | Build the StudyBuzz Docker image |
| `make run-app` | Build and run the Flask app container (standalone) |
| `make run-mistral` | Run the Mistral vLLM container |
| `make run-whisper` | Run the Whisper vLLM container |
| `make run-embedder` | Run the Nemotron-8B embedder container |
| `make run-db` | Run the PostgreSQL/pgvector database container |
| `make deploy` | Create a Podman pod and start **all** containers with sequenced model loading |
| `make update-app` | Fast restart of JUST the Flask app container (preserves running models) |
| `make update-whisper` | Restart just the Whisper container |
| `make clean` | Stop and remove all containers and the pod |

Common variables (override with `make VAR=value`):

```bash
make deploy HF_TOKEN=hf_xxx HUGGINGFACE_CACHE_PATH=/path/to/cache NUM_GPUS=8
```

> **Note**: `make deploy` waits for Mistral to pass its health check before starting Whisper and Nemotron, preventing VRAM spikes and NCCL collisions during concurrent model initialization.

---

## Database Schema

StudyBuzz uses PostgreSQL with the `pgvector` extension. The schema is managed by `init_db.py` and contains two tables:

**`lecture_videos`** — tracks each processed video

| Column | Type | Description |
|---|---|---|
| `id` | `BIGSERIAL` | Primary key |
| `video_hash` | `TEXT UNIQUE` | SHA-256 hash of the video file |
| `done_processing` | `BOOLEAN` | Whether the pipeline has completed |
| `note` | `TEXT` | Optional notes |
| `folder_path` | `TEXT` | Absolute path to the output directory |
| `video_name` | `TEXT` | Original filename |
| `video_date` | `TIMESTAMPTZ` | Timestamp of when the video was added |

**`chapter_embeddings`** — stores vector embeddings per chapter

| Column | Type | Description |
|---|---|---|
| `id` | `BIGSERIAL` | Primary key |
| `video_hash` | `TEXT` | Foreign key → `lecture_videos.video_hash` (cascade delete) |
| `chapter_path` | `TEXT` | Relative path to the chapter directory |
| `model_name` | `TEXT` | Embedding model used (e.g., `nemotron`) |
| `embedding` | `VECTOR(4096)` | 4096-dim embedding vector |
| `created_at` | `TIMESTAMPTZ` | Timestamp |

---

## Video Summary Pipeline (CLI)

The main code for the video summary pipeline is in `timeStampGen.py`. This script takes a video file as input and outputs a text summary of the video. It uses the VLLM server to run the Mistral model for video understanding. The VLLM server must be running before executing this script.

Run:
```bash
timeStampGen.py --help
```
to see the usage of the script. The main arguments are:

```
usage: timeStampGen.py [-h] [-d INPUT_DIR] [-o OUTPUT_DIR] [-f] [input_file]
```

| Flag | Description |
|---|---|
| `input_file` | Path to a single video file |
| `-d`, `--input-dir` | Directory of video files to batch process |
| `-o`, `--output-dir` | Output directory (default: `output`) |
| `-f`, `--force` | Reprocess even if the video is already marked complete in the database |

A sample command to run the script is as follows:
```bash
python timeStampGen.py lecture.mp4
```

### Semantic Search Tool

A standalone lookup script (`search.py`) is included to query the `chapter_embeddings` generated by the pipeline directly from the database using Postgres pgvector's cosine distance (`<=>`):

```bash
python search.py "Your question or keyword here" --limit 5
```

### Question Answering Tool (Multi-Hop RAG)

`question.py` builds on `search.py` to provide full question-answering over the lecture database using a multi-hop retrieval-augmented generation pipeline:

1. **Search** — Embeds the question via Nemotron and retrieves the top-k chapter matches from pgvector
2. **Per-result extraction** — Each chapter's transcript + summary is sent to Mistral **in parallel** to extract only the relevant information
3. **Final synthesis** — All per-chapter extractions are combined as context in one final LLM request to produce a comprehensive, cited answer

```bash
python question.py "What is gradient descent?" --top-k 5
```

| Flag | Description |
|---|---|
| `query` | The question to ask |
| `--top-k` | Number of search results to use (default: 5) |

> **Note:** Requires Mistral (port 8000), Nemotron (port 8002), and the pgvector database to be running.

---

## Project Structure

```
SB-V-1a/
├── app.py                      # Flask backend server
├── timeStampGen.py             # Main processing pipeline
├── search.py                   # CLI semantic search over chapter embeddings
├── question.py                 # Multi-hop RAG question answering over lectures
├── vllm_to_vtt.py              # VTT conversion utility
├── init_db.py                  # PostgreSQL database initialization & schema
├── bench.py                    # Benchmarking utility
├── run.sh                      # Convenience run script
├── requirements.txt            # Pipeline dependencies (httpx, openai)
├── requirements_backend.txt    # Backend dependencies (Flask, psycopg)
├── static/
│   └── index.html              # Minimal test frontend
├── Dockerfile                  # App container image definition
├── .dockerignore               # Docker build exclusions
├── Makefile                    # Podman container management targets
├── install.sh                  # One-time image pre-build (app + vLLM + pgvector)
├── manifest.yml                # Open OnDemand app registration
├── form.yml.erb                # OnDemand launch form
├── submit.yml.erb              # SLURM job parameters
├── view.html.erb               # OnDemand connect button
├── template/
│   ├── before.sh.erb           # Port allocation, env setup
│   ├── script.sh.erb           # Main deployment script (5 containers in a pod)
│   ├── after.sh                # Wait for app readiness
│   └── clean.sh                # Container cleanup
├── uploads/                     # Uploaded video files
└── output/                      # Generated artifacts
    └── <VIDEO_HASH>/            # Deterministic SHA-256 folder per video
        ├── source_video.mp4     # Original video copied here
        ├── full_transcript.vtt  # Raw Whisper transcript
        ├── timestamps.txt       # Raw Mistral timestamp generation
        ├── chapters_summary.json# Combined JSON of all summaries
        ├── chapter_01_Intro/    # Nested folder per chapter
        │   ├── transcript.vtt   # VTT slice for this chapter 
        │   ├── summary.json     # Summary for this chapter
        │   └── frames/          # Extracted visual frames
        └── chapter_02_Body/     # Next chapter...
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

From inside the app directory, run the install script to build the StudyBuzz Docker image and pull the vLLM and pgvector images. Fix CRLF line endings first if the code was edited on Windows.

```bash
sed -i 's/\r$//' install.sh

bash install.sh
```

This will:
1. Fix CRLF line endings on all deployment scripts
2. Build the StudyBuzz app image (Python + FFmpeg)
3. Pull the vLLM image (`vllm-openai:qwen3_5-x86_64-cu129`)
4. Pull the pgvector database image (`pgvector:pg18-trixie`)

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

> **Startup time:** The web interface is accessible within minutes. Mistral takes ~20 minutes to load, Whisper takes ~2 minutes. Video processing will not work until all three models finish loading. Use the **Service Health** check button in the UI to monitor readiness.

### How it works

```
Open OnDemand Dashboard
    │
    ▼ (SLURM job submission)
Compute Node (H200 HGX, 8 GPUs)
    │
    ├── Podman Pod (shared localhost network)
    │     ├── studybuzz-app container     ← Flask + FFmpeg (port 5000)
    │     ├── pgvector-local container    ← Postgres Vector DB (port 5432)
    │     ├── mistral-vllm container      ← Mistral-Large-3-675B (port 8000, 90% VRAM)
    │     ├── whisper-vllm container      ← Whisper-large-v3 (port 8001, 7.5% VRAM)
    │     └── nemotron-vllm container     ← Nemotron-8B (port 8002, 7% VRAM)
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

### Nemotron embedding errors

- Verify Nemotron is healthy: `curl http://localhost:8002/health`
- Check that `CUDA_VISIBLE_DEVICES` matches available GPUs on the node
- Ensure `VLLM_USE_V1=0` is set (required for embedding models)
- Check container logs: `podman logs studybuzz-embedder`
- The `--disable-custom-all-reduce` flag is required when co-locating with Mistral to avoid NCCL IPC conflicts

### NCCL collisions or IPC errors between vLLM containers

When running multiple vLLM instances on the same node, NCCL's custom all-reduce can cause IPC conflicts. Fix by adding `--disable-custom-all-reduce` to all vLLM containers sharing the same GPUs. The Makefile targets already include this flag.

---

## Acknowledgments

- [Mistral AI](https://mistral.ai/) — Mistral-Large-3
- [OpenAI Whisper](https://github.com/openai/whisper)
- [vLLM](https://github.com/vllm-project/vllm)
- [NVIDIA NeMo](https://github.com/NVIDIA/NeMo) — Nemotron-8B Embeddings
- Georgia Tech AI Makerspace (https://coe.gatech.edu/academics/ai-for-engineering/ai-makerspace)
- Open OnDemand (https://osc.github.io/ood-documentation/latest/)
