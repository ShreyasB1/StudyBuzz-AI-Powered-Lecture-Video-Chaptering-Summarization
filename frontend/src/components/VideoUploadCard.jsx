import React, { useMemo, useRef, useState } from 'react';
import StatusMessage from './StatusMessage.jsx';
import { buildApiUrl } from '../api.js';

function formatPercent(p) {
  if (p == null || Number.isNaN(p)) return null;
  const clamped = Math.max(0, Math.min(100, p));
  return `${Math.round(clamped)}%`;
}

export default function VideoUploadCard({ onUploaded }) {
  const fileRef = useRef(null);
  const [isUploading, setIsUploading] = useState(false);
  const [progressPct, setProgressPct] = useState(null);
  const [status, setStatus] = useState({ kind: 'info', text: '', visible: false });

  const progressText = useMemo(() => {
    const pct = formatPercent(progressPct);
    if (!isUploading) return null;
    if (!pct) return 'Uploading...';
    return `Uploading... ${pct}`;
  }, [isUploading, progressPct]);

  async function upload() {
    const file = fileRef.current?.files?.[0] ?? null;
    if (!file) {
      setStatus({ kind: 'error', text: 'Please select a video file.', visible: true });
      return;
    }

    setIsUploading(true);
    setProgressPct(null);
    setStatus({ kind: 'info', text: 'Uploading...', visible: true });

    const formData = new FormData();
    // API call: multipart/form-data POST to /api/upload, field name "file"
    formData.append('file', file);

    try {
      const result = await new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.open('POST', buildApiUrl('/upload'));

        xhr.upload.onprogress = (evt) => {
          if (!evt.lengthComputable) return;
          setProgressPct((evt.loaded / evt.total) * 100);
        };

        xhr.onload = () => {
          const contentType = xhr.getResponseHeader('content-type') || '';
          const isJson = contentType.includes('application/json');
          const body = isJson ? JSON.parse(xhr.responseText || '{}') : { raw: xhr.responseText };
          if (xhr.status >= 200 && xhr.status < 300) resolve(body);
          else reject(new Error(body?.error || `Upload failed (HTTP ${xhr.status})`));
        };
        xhr.onerror = () => reject(new Error('Network error'));
        xhr.send(formData);
      });

      setStatus({ kind: 'success', text: 'Upload complete.', visible: true });
      onUploaded?.(result);
    } catch (e) {
      setStatus({ kind: 'error', text: e?.message || 'Upload failed.', visible: true });
    } finally {
      setIsUploading(false);
      setProgressPct(null);
    }
  }

  return (
    <div className="card">
      <h2>Upload Video</h2>
      <label htmlFor="videoFile">Select a lecture video (MP4, MKV, MOV, AVI, WEBM)</label>
      <input
        ref={fileRef}
        type="file"
        id="videoFile"
        accept="video/*"
        disabled={isUploading}
      />
      <br />
      <button id="uploadBtn" onClick={upload} disabled={isUploading}>
        Upload &amp; Process
      </button>
      <StatusMessage kind={status.kind} hidden={!status.visible}>
        {progressText || status.text}
      </StatusMessage>
    </div>
  );
}

