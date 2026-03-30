import React, { useState, useEffect, useCallback } from 'react';
import { checkHealth, getGpuStatus } from '../services/api';

export default function DashboardPanel() {
  const [health, setHealth] = useState(null);
  const [healthLoading, setHealthLoading] = useState(false);
  const [healthError, setHealthError] = useState(null);

  const [gpus, setGpus] = useState([]);
  const [gpuLoading, setGpuLoading] = useState(false);
  const [gpuError, setGpuError] = useState(null);

  const fetchHealth = useCallback(async () => {
    setHealthLoading(true);
    setHealthError(null);
    try {
      const data = await checkHealth();
      setHealth(data);
    } catch (e) {
      setHealthError(e.message);
    } finally {
      setHealthLoading(false);
    }
  }, []);

  const fetchGpu = useCallback(async () => {
    setGpuLoading(true);
    setGpuError(null);
    try {
      const data = await getGpuStatus();
      setGpus(data.gpus || []);
    } catch (e) {
      setGpuError(e.message);
    } finally {
      setGpuLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchHealth();
    fetchGpu();
  }, [fetchHealth, fetchGpu]);

  function statusClass(s) {
    return s === 'ready' || s === 'healthy' ? 'ready' : 'not-ready';
  }

  function meterClass(pct) {
    if (pct < 50) return 'low';
    if (pct < 80) return 'medium';
    return 'high';
  }

  return (
    <>
      {/* Service Health */}
      <div className="card">
        <div className="card-header">
          <div>
            <div className="card-title">Service Health</div>
            <div className="card-subtitle">Monitor the status of all backend services</div>
          </div>
          <button className="btn btn-secondary btn-sm" onClick={fetchHealth} disabled={healthLoading}>
            {healthLoading ? 'Checking...' : 'Refresh'}
          </button>
        </div>

        {healthError && <div className="status-msg error">{healthError}</div>}

        {health && !healthError && (
          <div className="health-grid">
            {[
              { label: 'StudyBuzz App', status: health.status },
              { label: 'Mistral LLM', status: health.mistral },
              { label: 'Whisper STT', status: health.whisper },
              { label: 'Nemotron Embeddings', status: health.nemotron },
            ].map((svc) => (
              <div key={svc.label} className="health-item">
                <div className={`health-dot ${statusClass(svc.status)}`} />
                <div>
                  <div className="health-value">{svc.status || 'unknown'}</div>
                  <div className="health-label">{svc.label}</div>
                </div>
              </div>
            ))}
          </div>
        )}

        {health && health.mistral === 'ready' && health.whisper === 'ready' && health.nemotron === 'ready' && (
          <div className="status-msg success" style={{ marginTop: '1rem' }}>
            All models loaded and ready to process videos.
          </div>
        )}
      </div>

      {/* GPU Status */}
      <div className="card">
        <div className="card-header">
          <div>
            <div className="card-title">GPU Status</div>
            <div className="card-subtitle">Real-time GPU utilization and memory</div>
          </div>
          <button className="btn btn-secondary btn-sm" onClick={fetchGpu} disabled={gpuLoading}>
            {gpuLoading ? 'Loading...' : 'Refresh'}
          </button>
        </div>

        {gpuError && <div className="status-msg error">{gpuError}</div>}

        {gpus.length > 0 && (
          <div className="gpu-grid">
            {gpus.map((g) => (
              <div key={g.index} className="gpu-card">
                <div className="gpu-card-header">
                  <span className="gpu-name">GPU {g.index}: {g.name}</span>
                  <span className="gpu-temp">{g.temperature_c}°C</span>
                </div>
                <div className="gpu-meter">
                  <div className="gpu-meter-label">
                    <span>Utilization</span>
                    <span>{g.utilization_pct}%</span>
                  </div>
                  <div className="gpu-meter-track">
                    <div className={`gpu-meter-fill ${meterClass(g.utilization_pct)}`} style={{ width: `${g.utilization_pct}%` }} />
                  </div>
                </div>
                <div className="gpu-meter">
                  <div className="gpu-meter-label">
                    <span>Memory</span>
                    <span>{g.memory_used_mb}/{g.memory_total_mb} MB ({g.memory_pct}%)</span>
                  </div>
                  <div className="gpu-meter-track">
                    <div className={`gpu-meter-fill ${meterClass(g.memory_pct)}`} style={{ width: `${g.memory_pct}%` }} />
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {!gpuLoading && !gpuError && gpus.length === 0 && (
          <div className="empty-state">
            <div className="empty-state-text">No GPU data available. Click Refresh to check.</div>
          </div>
        )}
      </div>
    </>
  );
}
