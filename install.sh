#!/usr/bin/env bash
set -e

export XDG_RUNTIME_DIR="/tmp/run-$(id -u)"
mkdir -p "$XDG_RUNTIME_DIR"
chmod 700 "$XDG_RUNTIME_DIR"

echo "Fixing line endings (CRLF -> LF) on all deployment files..."
for f in \
  Dockerfile Makefile install.sh \
  manifest.yml form.yml.erb submit.yml.erb view.html.erb \
  template/before.sh.erb template/script.sh.erb template/after.sh template/clean.sh; do
  if [ -f "$f" ]; then
    sed -i 's/\r$//' "$f"
  fi
done

echo "Setting execute permissions on scripts..."
chmod +x template/script.sh.erb template/clean.sh template/after.sh install.sh

echo "Building StudyBuzz Docker image..."
make build-app

echo "Pulling vLLM Docker image..."
podman pull docker.io/vllm/vllm-openai:latest

echo "Install complete. Images are ready."
