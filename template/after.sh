# Wait for the StudyBuzz Flask server to start.
# The Flask app should come up within a few minutes (after the Docker image
# build completes). vLLM model loading happens in the background and does NOT
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
  echo "=== vLLM Logs ==="
  podman logs "vllm-${SLURM_JOB_ID}" 2>&1 | tail -50 || true
  echo "=== Pod Status ==="
  podman pod ps 2>&1 || true
  podman ps -a 2>&1 || true
fi

sleep 2
