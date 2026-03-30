# Wait for the StudyBuzz Flask server to start.
# The Flask app should come up within a few minutes (after the Docker image
# build completes). Model loading happens in the background and does NOT
# block the web UI from starting.
echo "Waiting for StudyBuzz server to open port ${port}..."
echo "TIMING - Starting wait at: $(date)"

if wait_until_port_used "${host}:${port}" 600; then
  echo "Discovered StudyBuzz server listening on port ${port}!"
  echo "TIMING - Wait ended at: $(date)"
else
  echo "Timed out waiting for StudyBuzz server to open port ${port}!"
  echo "TIMING - Wait ended at: $(date)"

  echo "=== StudyBuzz App Logs ==="
  podman logs "studybuzz-app-${SLURM_JOB_ID}" 2>&1 || true
  echo "=== Mistral vLLM Logs ==="
  podman logs "mistral-vllm-${SLURM_JOB_ID}" 2>&1 | tail -50 || true
  echo "=== Whisper vLLM Logs ==="
  podman logs "whisper-vllm-${SLURM_JOB_ID}" 2>&1 | tail -50 || true
  echo "=== Nemotron vLLM Logs ==="
  podman logs "nemotron-vllm-${SLURM_JOB_ID}" 2>&1 | tail -50 || true
  echo "=== PostgreSQL Logs ==="
  podman logs "pgvector_local-${SLURM_JOB_ID}" 2>&1 | tail -20 || true
  echo "=== Pod Status ==="
  podman pod ps 2>&1 || true
  podman ps -a 2>&1 || true
fi

sleep 2
