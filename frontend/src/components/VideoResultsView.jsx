import React, { useState, useEffect, useCallback } from 'react';
import { getResultsByHash, getJobResults, getVideoStreamUrlByHash, getVideoStreamUrl } from '../services/api';

export default function VideoResults({ video, onBack }) {
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeSection, setActiveSection] = useState('chapters');

  const fetchResults = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      let data;
      if (video.source === 'job' && video.jobId) {
        data = await getJobResults(video.jobId);
      } else if (video.hash) {
        data = await getResultsByHash(video.hash);
      } else {
        throw new Error('No video identifier provided');
      }
      setResults(data);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [video]);

  useEffect(() => {
    fetchResults();
  }, [fetchResults]);

  const videoStreamUrl = video.hash
    ? getVideoStreamUrlByHash(video.hash)
    : video.jobId
      ? getVideoStreamUrl(video.jobId)
      : null;

  const sections = [];
  if (videoStreamUrl) sections.push('video');
  sections.push('chapters', 'summaries', 'transcript');

  return (
    <>
      <button className="back-link" onClick={onBack}>← Back</button>

      <div className="card">
        <div className="card-header">
          <div>
            <div className="card-title">{video.name || 'Video Results'}</div>
            <div className="card-subtitle">AI-generated chapters, summaries, and transcript</div>
          </div>
        </div>

        {loading && (
          <div className="loading-state">
            <div className="spinner" />
            <span>Loading results...</span>
          </div>
        )}

        {error && <div className="status-msg error">{error}</div>}

        {results && !loading && (
          <>
            <div className="section-tabs">
              {sections.map((s) => (
                <button
                  key={s}
                  className={`section-tab${activeSection === s ? ' active' : ''}`}
                  onClick={() => setActiveSection(s)}
                >
                  {s.charAt(0).toUpperCase() + s.slice(1)}
                </button>
              ))}
            </div>

            {activeSection === 'video' && videoStreamUrl && (
              <div className="video-player-container">
                <video controls src={videoStreamUrl} />
              </div>
            )}

            {activeSection === 'chapters' && (
              results.timestamps && results.timestamps.length > 0 ? (
                <div className="chapter-list">
                  {results.timestamps.map((ch, i) => (
                    <div key={i} className="chapter-item">
                      <div className="chapter-time">{ch.time}</div>
                      <div className="chapter-title">{ch.title}</div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="empty-state">
                  <div className="empty-state-text">No chapters available.</div>
                </div>
              )
            )}

            {activeSection === 'summaries' && (
              results.summary && results.summary.length > 0 ? (
                <div className="chapter-list">
                  {results.summary.map((item, idx) => (
                    <React.Fragment key={idx}>
                      {Object.entries(item).map(([time, summaries]) =>
                        Object.entries(summaries).map(([title, text]) => (
                          <div key={`${idx}-${time}-${title}`} className="chapter-item">
                            <div className="chapter-time">{time}</div>
                            <div className="chapter-title">{title}</div>
                            <div className="chapter-summary">{text}</div>
                          </div>
                        ))
                      )}
                    </React.Fragment>
                  ))}
                </div>
              ) : (
                <div className="empty-state">
                  <div className="empty-state-text">No summaries available.</div>
                </div>
              )
            )}

            {activeSection === 'transcript' && (
              results.transcript ? (
                <div className="transcript-box">{results.transcript}</div>
              ) : (
                <div className="empty-state">
                  <div className="empty-state-text">No transcript available.</div>
                </div>
              )
            )}
          </>
        )}
      </div>
    </>
  );
}
