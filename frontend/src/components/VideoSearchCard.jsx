import React, { useMemo, useState } from 'react';
import StatusMessage from './StatusMessage.jsx';
import { buildApiUrl } from '../api.js';

function formatDuration(seconds) {
  if (seconds == null) return '';
  const s = Number(seconds);
  if (Number.isNaN(s) || !Number.isFinite(s)) return String(seconds);
  const whole = Math.max(0, Math.floor(s));
  const hh = Math.floor(whole / 3600);
  const mm = Math.floor((whole % 3600) / 60);
  const ss = whole % 60;
  const pad = (n) => String(n).padStart(2, '0');
  return hh > 0 ? `${hh}:${pad(mm)}:${pad(ss)}` : `${mm}:${pad(ss)}`;
}

export default function VideoSearchCard() {
  const [query, setQuery] = useState('');
  const [isSearching, setIsSearching] = useState(false);
  const [status, setStatus] = useState({ kind: 'info', text: '', visible: false });
  const [results, setResults] = useState([]);

  const trimmedQuery = useMemo(() => query.trim(), [query]);

  async function doSearch() {
    if (!trimmedQuery) {
      setStatus({ kind: 'error', text: 'Please enter a search query.', visible: true });
      setResults([]);
      return;
    }

    setIsSearching(true);
    setStatus({ kind: 'info', text: 'Searching...', visible: true });

    try {
      // API call: GET /api/search?q={query}
      const url = new URL(buildApiUrl('/search'), window.location.origin);
      url.searchParams.set('q', trimmedQuery);

      const res = await fetch(url.toString(), { method: 'GET' });
      const data = await res.json().catch(() => ({}));

      if (!res.ok) throw new Error(data?.error || `Search failed (HTTP ${res.status})`);

      const items = Array.isArray(data) ? data : Array.isArray(data?.results) ? data.results : [];
      setResults(items);

      if (!items.length) {
        setStatus({ kind: 'warn', text: 'No results found.', visible: true });
      } else {
        setStatus({ kind: 'success', text: `Found ${items.length} result(s).`, visible: true });
      }
    } catch (e) {
      setResults([]);
      setStatus({ kind: 'error', text: e?.message || 'Search failed.', visible: true });
    } finally {
      setIsSearching(false);
    }
  }

  function onKeyDown(e) {
    if (e.key === 'Enter') doSearch();
  }

  return (
    <div className="card">
      <h2>Search Videos</h2>
      <label htmlFor="searchQuery">Search query</label>
      <input
        id="searchQuery"
        type="text"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onKeyDown={onKeyDown}
        disabled={isSearching}
        style={{
          width: '100%',
          padding: '0.6rem 0.75rem',
          borderRadius: 4,
          border: '1px solid #ddd'
        }}
      />
      <div style={{ marginTop: '0.75rem' }}>
        <button onClick={doSearch} disabled={isSearching}>
          Search
        </button>
      </div>

      <StatusMessage kind={status.kind} hidden={!status.visible}>
        {status.text}
      </StatusMessage>

      <div className={`results${results.length ? '' : ' hidden'}`}>
        <h3>Results</h3>
        {results.map((r) => (
          <div key={r.id} className="result-item">
            <img className="result-thumb" src={r.thumbnail_url} alt={r.title} />
            <div className="result-meta">
              <div className="result-title">{r.title}</div>
              <div className="result-duration">{formatDuration(r.duration)}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

