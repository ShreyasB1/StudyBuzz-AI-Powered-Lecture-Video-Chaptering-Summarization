import React, { useState } from 'react';
import StatusMessage from './StatusMessage.jsx';
import { buildApiUrl } from '../api.js';

function formatNumber(n) {
  if (n == null) return '';
  return String(n);
}

export default function GpuStatusCard() {
  const [gpus, setGpus] = useState([]);
  const [status, setStatus] = useState({ kind: 'info', text: '', visible: false });
  const [isLoading, setIsLoading] = useState(false);

  async function check() {
    setIsLoading(true);
    setStatus({ kind: 'info', text: 'Checking GPU status...', visible: true });
    setGpus([]);

    try {
      // API call: GET /api/gpu-status (backend runs nvidia-smi)
      const res = await fetch(buildApiUrl('/gpu-status'), { method: 'GET' });
      const data = await res.json().catch(() => ({}));

      if (!res.ok) {
        throw new Error(data?.error || `GPU status failed (HTTP ${res.status})`);
      }

      const items = Array.isArray(data?.gpus) ? data.gpus : [];
      setGpus(items);

      if (!items.length) {
        setStatus({ kind: 'warn', text: 'No GPUs reported.', visible: true });
      } else {
        setStatus({
          kind: 'success',
          text: `GPU status ready (${items.length} GPU${items.length === 1 ? '' : 's'}).`,
          visible: true
        });
      }
    } catch (e) {
      setStatus({ kind: 'error', text: e?.message || 'Failed to load GPU status.', visible: true });
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="card">
      <h2>GPU Status</h2>
      <button onClick={check} disabled={isLoading}>
        {isLoading ? 'Checking...' : 'Check GPU Status'}
      </button>
      <StatusMessage kind={status.kind} hidden={!status.visible}>
        {status.text}
      </StatusMessage>

      <div style={{ marginTop: '0.75rem' }}>
        {gpus.map((g) => (
          <div key={g.index} className="health-row">
            <span className={`dot ${g.utilization_pct >= 20 ? 'red' : 'gray'}`} />
            GPU {formatNumber(g.index)}: {g.name}
            {' — '}
            {formatNumber(g.utilization_pct)}% util
            {' — '}
            {formatNumber(g.memory_used_mb)}/{formatNumber(g.memory_total_mb)} MB
            {' '}
            ({formatNumber(g.memory_pct)}% used)
            {' — '}
            {formatNumber(g.temperature_c)}C
          </div>
        ))}
      </div>
    </div>
  );
}

