# M-SB-TUT-Stud-1
This branch holds the code for running the video summary pipeline.

There are may components in this codebase:

# VLLM
VLLM is used for running the large language model and the transcription model. 
We are using Mistral-Large-3 for reasoning and whisper-large-v3 for transcription.

We use podman to run the VLLM servers. We choose podman over a conventional local pip install to avoid dependency issues.

The command to run the VLLM server for Mistral-Large-3 is as follows:

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

The command to run the VLLM server for Whisper is as follows:

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

The command must be run in the output directory (create it if it does not exist) where the `timeStampGen.py` script will output the intermediate files. There must also be a video directory in the output directory where the input video is stored.

# Video Summary Pipeline
The main code for the video summary pipeline is in `timeStampGen.py`. This script takes a video file as input and outputs a text summary of the video. It uses the VLLM server to run the Mistral model for video understanding. The VLLM server must be running before executing this script.

This script also requires a few other dependencies. 

## FFmpeg
FFmpeg is used for video processing and extracting frames. A binary must be on the system PATH for the script to work. 

## Python Dependencies
We recommend creating a virtual environment for the python dependencies. The dependencies can be installed using the `requirements.txt` file in this directory:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Run:
```bash
timeStampGen.py --help
``` 
to see the usage of the script. The main arguments are:
```
usage: timeStampGen.py [-h] [-d INPUT_DIR] [-o OUTPUT_DIR] [input_file]
timeStampGen.py: error: Either provide an input_file or --input-dir with video files to process.
```

A sample command to run the script is as follows:
```bash
python timeStampGen.py lecture.mp4
```
