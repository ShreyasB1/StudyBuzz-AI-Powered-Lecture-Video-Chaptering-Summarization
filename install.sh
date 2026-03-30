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

echo "Pulling base images in parallel..."

podman pull docker.io/library/node:20-slim &
PID_PULL_NODE=$!

podman pull docker.io/vllm/vllm-openai:qwen3_5-x86_64-cu129 &
PID_PULL_VLLM=$!

podman pull docker.io/pgvector/pgvector:pg18-trixie &
PID_PULL_DB=$!

wait $PID_PULL_NODE
echo "  Node.js image ready."

wait $PID_PULL_VLLM
echo "  vLLM image ready."

wait $PID_PULL_DB
echo "  pgvector image ready."

# Build React frontend in a separate container (multi-stage builds break
# on rootless Podman without subuid ranges)
if [ -d "frontend/src" ]; then
  echo "Building React frontend..."
  podman run --rm \
    -v "$(pwd)/frontend:/app:Z" \
    -w /app \
    docker.io/library/node:20-slim \
    sh -c "npm install && npm run build"
  echo "  Frontend built."
fi

echo "Building StudyBuzz app image..."
make build-app
echo "  App image built."

echo "Install complete. All images are ready."
