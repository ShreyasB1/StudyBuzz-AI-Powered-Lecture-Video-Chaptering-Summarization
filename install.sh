#!/usr/bin/env bash
set -e

export XDG_RUNTIME_DIR="/tmp/run-$(id -u)"
mkdir -p "$XDG_RUNTIME_DIR"
chmod 700 "$XDG_RUNTIME_DIR"

echo "Fixing line endings (CRLF -> LF) on all deployment files..."
for f in \
  Dockerfile .dockerignore Makefile install.sh \
  manifest.yml form.yml.erb submit.yml.erb view.html.erb \
  template/before.sh.erb template/script.sh.erb template/after.sh template/clean.sh; do
  if [ -f "$f" ]; then
    sed -i 's/\r$//' "$f"
  fi
done

echo "Setting execute permissions on scripts..."
chmod +x template/script.sh.erb template/clean.sh template/after.sh install.sh

echo "Building StudyBuzz Docker image and pulling vLLM & DB images in parallel..."

make build-app &
PID_BUILD=$!

podman pull docker.io/vllm/vllm-openai:qwen3_5-x86_64-cu129 &
PID_PULL_VLLM=$!

podman pull pgvector/pgvector:pg18-trixie &
PID_PULL_DB=$!

# Wait for all background processes to finish
wait $PID_BUILD
wait $PID_PULL_VLLM
wait $PID_PULL_DB

echo "Install complete. All images are ready."
