#!/usr/bin/env bash

echo "Job ending - cleaning up StudyBuzz containers..."

# Stop and remove all containers
podman stop "studybuzz-app-${SLURM_JOB_ID}" "mistral-vllm-${SLURM_JOB_ID}" "whisper-vllm-${SLURM_JOB_ID}" "pgvector_local-${SLURM_JOB_ID}" 2>/dev/null || true
podman rm "studybuzz-app-${SLURM_JOB_ID}" "mistral-vllm-${SLURM_JOB_ID}" "whisper-vllm-${SLURM_JOB_ID}" "pgvector_local-${SLURM_JOB_ID}" 2>/dev/null || true

# Remove the pod
podman pod rm -f "studybuzz-pod-${SLURM_JOB_ID}" 2>/dev/null || true

# Remove the built image to save space
podman rmi "studybuzz-app-${SLURM_JOB_ID}" 2>/dev/null || true

# Clean up Podman storage directory
rm -rf "${PODMAN_STORAGE_ROOT}" 2>/dev/null || true

echo "Cleanup complete."
