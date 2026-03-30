import React, { useState } from 'react';
import { searchVideos } from '../services/api';

export default function SearchPanel({ onViewVideo }) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState(null);
  const [searched, setSearched] = useState(false);

  async function handleSearch() {
    const trimmed = query.trim();
    if (!trimmed) {
      setStatus({ type: 'warning', text: 'Please enter a search query.' });
      return;
    }

    setLoading(true);
    setStatus(null);
    setSearched(true);

    try {
      const data = await searchVideos(trimmed);
      const items = Array.isArray(data) ? data : Array.isArray(data?.results) ? data.results : [];
      setResults(items);

      if (items.length === 0) {
        setStatus({ type: 'warning', text: 'No results found.' });
      } else {
        setStatus({ type: 'success', text: `Found ${items.length} result(s).` });
      }
    } catch (e) {
      setResults([]);
      setStatus({ type: 'error', text: e.message });
    } finally {
      setLoading(false);
    }
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter') handleSearch();
  }

  return (
    <div className="card">
      <div className="card-header">
        <div>
          <div className="card-title">Search Videos</div>
          <div className="card-subtitle">Find lecture videos by name</div>
        </div>
      </div>

      <div className="search-bar">
        <input
          className="form-input"
          type="text"
          placeholder="Search for a video..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={loading}
        />
        <button className="btn btn-primary" onClick={handleSearch} disabled={loading}>
          {loading ? 'Searching...' : 'Search'}
        </button>
      </div>

      {status && <div className={`status-msg ${status.type}`}>{status.text}</div>}

      {results.length > 0 && (
        <div className="search-results">
          {results.map((r, i) => {
            const prettyChapter = r.chapter_path ? r.chapter_path.replace(/^chapter_\d+_/, '').replace(/_/g, ' ') : '';
            return (
              <div
                key={`${r.hash}-${i}`}
                className="search-result-item"
                onClick={() => onViewVideo({ hash: r.hash, name: r.video_name, source: 'search', chapterPath: r.chapter_path })}
              >
                <div className="video-icon">🎯</div>
                <div className="video-meta">
                  <div className="video-name">{prettyChapter || 'Chapter Match'}</div>
                  <div style={{ fontSize: '0.85em', color: 'var(--text-muted)' }}>
                    From: {r.video_name} (Match: {Math.round(r.similarity * 100)}%)
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {searched && !loading && results.length === 0 && status?.type !== 'error' && (
        <div className="empty-state">
          <div className="empty-state-icon">🔍</div>
          <div className="empty-state-title">No results found</div>
          <div className="empty-state-text">Try a different search term.</div>
        </div>
      )}
    </div>
  );
}
