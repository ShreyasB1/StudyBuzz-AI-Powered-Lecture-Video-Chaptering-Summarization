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

# Build React frontend in a separate container
if [ -d "frontend/src" ]; then
  echo "Building React frontend..."
  podman run --rm \
    -v "$(pwd)/frontend:/app:Z" \
    -w /app \
    docker.io/library/node:20-slim \
    sh -c "npm install && npm run build"
  echo "  Frontend built."
fi

# Build app image using podman run + commit (podman build is broken
# on PACE's rootless Podman — crun cannot find /bin/sh in build containers)
echo "Building StudyBuzz app image..."

BUILD_CTR="studybuzz-build-install"
podman rm -f "${BUILD_CTR}" 2>/dev/null || true

podman run -d \
  --name "${BUILD_CTR}" \
  python:3.11-slim \
  sleep infinity

podman exec "${BUILD_CTR}" sh -c "\
  apt-get -o APT::Sandbox::User=root update && \
  apt-get -o APT::Sandbox::User=root install -y --no-install-recommends ffmpeg && \
  rm -rf /var/lib/apt/lists/*"

podman cp requirements.txt "${BUILD_CTR}:/app/"
podman cp requirements_backend.txt "${BUILD_CTR}:/app/"

podman exec "${BUILD_CTR}" sh -c "\
  cd /app && pip install --upgrade pip && \
  pip install -r requirements.txt && \
  pip install -r requirements_backend.txt"

for f in app.py timeStampGen.py vllm_to_vtt.py init_db.py; do
  podman cp "${f}" "${BUILD_CTR}:/app/"
done

podman cp static "${BUILD_CTR}:/app/static"

if [ -d "frontend/dist" ]; then
  podman exec "${BUILD_CTR}" mkdir -p /app/frontend
  podman cp frontend/dist "${BUILD_CTR}:/app/frontend/dist"
fi

podman exec "${BUILD_CTR}" mkdir -p /app/uploads /app/output/video

podman commit \
  -c 'WORKDIR /app' \
  -c 'ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 BUILD_FRONTEND=0' \
  -c 'EXPOSE 5000' \
  -c 'CMD ["sh", "-c", "python init_db.py && python app.py"]' \
  "${BUILD_CTR}" \
  studybuzz-app

podman rm -f "${BUILD_CTR}"
echo "  App image built."

echo "Install complete. All images are ready."
