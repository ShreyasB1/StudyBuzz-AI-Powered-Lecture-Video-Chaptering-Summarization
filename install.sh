#!/usr/bin/env bash
set -e

export XDG_RUNTIME_DIR="/tmp/run-$(id -u)"
mkdir -p "$XDG_RUNTIME_DIR"
chmod 700 "$XDG_RUNTIME_DIR"

echo "Building StudyBuzz Docker image..."
make build-app

echo "Pulling vLLM Docker image..."
podman pull docker.io/vllm/vllm-openai:latest

echo "Install complete. Images are ready."
