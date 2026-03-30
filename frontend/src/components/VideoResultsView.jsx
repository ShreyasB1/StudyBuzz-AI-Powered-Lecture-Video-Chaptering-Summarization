import React, { useState, useEffect, useCallback, useRef } from 'react';
import { getResultsByHash, getJobResults, getVideoStreamUrlByHash, getVideoStreamUrl } from '../services/api';

export default function VideoResults({ video, onBack }) {
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeSection, setActiveSection] = useState('chapters');
  const videoRef = useRef(null);

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

  const [hasSought, setHasSought] = useState(false);

  useEffect(() => {
    setHasSought(false);
  }, [video.chapterPath]);

  useEffect(() => {
    if (!video.chapterPath || !results?.timestamps || !videoRef.current || activeSection !== 'video' || hasSought) return;

    // chapterPath is usually like "chapter_01_Introduction"
    // Extract the index from it
    const match = video.chapterPath.match(/^chapter_(\d+)_/);
    if (match) {
      const idx = parseInt(match[1], 10) - 1; // 1-based to 0-based
      if (idx >= 0 && idx < results.timestamps.length) {
        const timeStr = results.timestamps[idx].time; 
        
        // Parse time string to seconds (e.g. "00:01:23,456" or "01:23" or "01:23.456")
        let seconds = 0;
        const cleanTime = timeStr.split(/[,\.]/)[0].trim();
        const timeMain = cleanTime.split(':');
        if (timeMain.length === 3) {
          seconds = parseInt(timeMain[0], 10) * 3600 + parseInt(timeMain[1], 10) * 60 + parseInt(timeMain[2], 10);
        } else if (timeMain.length === 2) {
          seconds = parseInt(timeMain[0], 10) * 60 + parseInt(timeMain[1], 10);
        }
        
        // Autoplay and seek once video metadata is loaded
        const onLoadedMetadata = () => {
          videoRef.current.currentTime = seconds;
          videoRef.current.play().catch(e => console.warn('Autoplay prevented:', e));
          setHasSought(true); // Don't re-seek if video re-renders
        };

        if (videoRef.current.readyState >= 1) { // HAVE_METADATA
          onLoadedMetadata();
        } else {
          videoRef.current.addEventListener('loadedmetadata', onLoadedMetadata, { once: true });
        }
      }
    }
  }, [video.chapterPath, results, activeSection, hasSought]);

  // Set initial section to 'video' if navigating from search
  useEffect(() => {
    if (video.source === 'search' && activeSection !== 'video' && videoStreamUrl) {
      setActiveSection('video');
    }
  }, [video.source, videoStreamUrl]);

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
                <video ref={videoRef} controls src={videoStreamUrl} />
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
