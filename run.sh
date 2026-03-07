#!/usr/bin/env bash
# run.sh - Quick test deployment wrapper for interactive SSH sessions

HF_TOKEN=${1:-$HUGGING_FACE_HUB_TOKEN}
if [ -z "$HF_TOKEN" ]; then
    echo "ERROR: HuggingFace token required."
    echo "Usage: ./run.sh <HF_TOKEN>"
    echo "Or set HUGGING_FACE_HUB_TOKEN in your environment."
    exit 1
fi

CACHE_PATH="/storage/ice-shared/vip-vp4/Spring2026/SB-V-1a/huggingface"

echo "Starting StudyBuzz Interactive Dev Session on $(hostname)"

# Setup Podman rootless runtime
export XDG_RUNTIME_DIR="/tmp/run-$(id -u)"
mkdir -p "$XDG_RUNTIME_DIR"
chmod 700 "$XDG_RUNTIME_DIR"

# Clean up any existing containers
make clean

# Deploy the containers
echo "Deploying via Makefile..."
make deploy HF_TOKEN="${HF_TOKEN}" NUM_GPUS=8 HUGGINGFACE_CACHE_PATH="${CACHE_PATH}"

echo "=========================================================="
echo "StudyBuzz is running!"
echo "Access the app at: http://$(hostname):5000"
echo "Access Mistral at: http://$(hostname):8000"
echo "Access Whisper at: http://$(hostname):8001"
echo "To view app logs: podman logs -f studybuzz-app"
echo "=========================================================="
