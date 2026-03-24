import React, { useState, useEffect, useCallback } from 'react';
import { listVideos } from '../services/api';

export default function LibraryPanel({ onViewVideo }) {
  const [videos, setVideos] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchVideos = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listVideos();
      setVideos(data.videos || []);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchVideos();
  }, [fetchVideos]);

  function formatDate(dateStr) {
    if (!dateStr) return '';
    try {
      return new Date(dateStr).toLocaleDateString('en-US', {
        year: 'numeric', month: 'short', day: 'numeric',
      });
    } catch {
      return dateStr;
    }
  }

  return (
    <div className="card">
      <div className="card-header">
        <div>
          <div className="card-title">Video Library</div>
          <div className="card-subtitle">All processed lecture videos</div>
        </div>
        <button className="btn btn-secondary btn-sm" onClick={fetchVideos} disabled={loading}>
          {loading ? 'Loading...' : 'Refresh'}
        </button>
      </div>

      {error && <div className="status-msg error">{error}</div>}

      {loading && videos.length === 0 && (
        <div className="loading-state">
          <div className="spinner" />
          <span>Loading videos...</span>
        </div>
      )}

      {!loading && !error && videos.length === 0 && (
        <div className="empty-state">
          <div className="empty-state-icon">📚</div>
          <div className="empty-state-title">No videos yet</div>
          <div className="empty-state-text">Upload a video to get started with AI-powered chaptering.</div>
        </div>
      )}

      {videos.length > 0 && (
        <div className="video-list">
          {videos.map((v) => (
            <div
              key={v.video_hash}
              className="video-item"
              onClick={() => onViewVideo({ hash: v.video_hash, name: v.video_name, source: 'library' })}
            >
              <div className="video-icon">🎬</div>
              <div className="video-meta">
                <div className="video-name">{v.video_name}</div>
                <div className="video-date">{formatDate(v.video_date)}</div>
              </div>
              <span className={`video-badge ${v.done_processing ? 'done' : 'processing'}`}>
                {v.done_processing ? 'Processed' : 'Processing'}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
