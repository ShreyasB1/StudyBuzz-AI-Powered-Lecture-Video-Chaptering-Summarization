# Wait for the StudyBuzz Flask server to start
echo "Waiting for StudyBuzz server to open port ${port}..."
echo "TIMING - Starting wait at: $(date)"

if wait_until_port_used "${host}:${port}" 120; then
  echo "Discovered StudyBuzz server listening on port ${port}!"
  echo "TIMING - Wait ended at: $(date)"
else
  echo "Timed out waiting for StudyBuzz server to open port ${port}!"
  echo "TIMING - Wait ended at: $(date)"

  echo "=== StudyBuzz App Logs ==="
  podman logs "studybuzz-app-${SLURM_JOB_ID}" 2>&1
  echo "=== vLLM Logs ==="
  podman logs "vllm-${SLURM_JOB_ID}" 2>&1 | tail -50

  podman stop "studybuzz-app-${SLURM_JOB_ID}" "vllm-${SLURM_JOB_ID}" 2>/dev/null
  podman rm "studybuzz-app-${SLURM_JOB_ID}" "vllm-${SLURM_JOB_ID}" 2>/dev/null

  pkill -P ${SCRIPT_PID}
  clean_up 1
fi

sleep 2
