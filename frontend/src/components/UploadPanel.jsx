import React, { useRef, useState, useEffect } from 'react';
import { uploadVideo, getJobStatus, getPipelineLog, getJobResults } from '../services/api';

export default function UploadPanel({ onViewResults }) {
  const fileRef = useRef(null);
  const [selectedFile, setSelectedFile] = useState(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [status, setStatus] = useState(null);

  const [jobId, setJobId] = useState(null);
  const [jobStatus, setJobStatus] = useState(null);
  const [jobProgress, setJobProgress] = useState('');

  const [logContent, setLogContent] = useState(null);
  const [showLog, setShowLog] = useState(false);

  // Poll job status
  useEffect(() => {
    if (!jobId) return;

    const interval = setInterval(async () => {
      try {
        const data = await getJobStatus(jobId);
        setJobStatus(data.status);
        setJobProgress(data.progress || data.status || '');

        if (data.status === 'completed') {
          clearInterval(interval);
          setStatus({ type: 'success', text: 'Processing complete! Click "View Results" to see chapters and summaries.' });
        } else if (data.status === 'failed') {
          clearInterval(interval);
          setStatus({ type: 'error', text: data.error || 'Processing failed.' });
        }
      } catch {
        // silently retry on next tick
      }
    }, 3000);

    return () => clearInterval(interval);
  }, [jobId]);

  function handleFileSelect(e) {
    setSelectedFile(e.target.files?.[0] || null);
  }

  async function handleUpload() {
    if (!selectedFile) {
      setStatus({ type: 'error', text: 'Please select a video file.' });
      return;
    }

    setIsUploading(true);
    setUploadProgress(0);
    setStatus({ type: 'info', text: 'Uploading video...' });
    setJobId(null);
    setJobStatus(null);
    setJobProgress('');
    setLogContent(null);
    setShowLog(false);

    try {
      const result = await uploadVideo(selectedFile, (pct) => setUploadProgress(pct));
      setJobId(result.job_id);
      setJobStatus('processing');
      setJobProgress('Video uploaded. Processing started...');
      setStatus({ type: 'info', text: `Processing started (Job: ${result.job_id.slice(0, 8)}...)` });
    } catch (e) {
      setStatus({ type: 'error', text: e.message });
    } finally {
      setIsUploading(false);
      setUploadProgress(0);
    }
  }

  async function handleViewLog() {
    if (!jobId) return;
    if (showLog) { setShowLog(false); return; }
    try {
      const data = await getPipelineLog(jobId);
      setLogContent(data.log || 'No log content.');
      setShowLog(true);
    } catch (e) {
      setLogContent(`Error loading log: ${e.message}`);
      setShowLog(true);
    }
  }

  async function handleViewResults() {
    if (!jobId) return;
    try {
      const data = await getJobResults(jobId);
      onViewResults({
        hash: data.video_hash || null,
        name: data.video_filename || selectedFile?.name || 'Video',
        source: 'job',
        jobId,
      });
    } catch (e) {
      setStatus({ type: 'error', text: e.message });
    }
  }

  return (
    <>
      {/* Upload Card */}
      <div className="card">
        <div className="card-header">
          <div>
            <div className="card-title">Upload Video</div>
            <div className="card-subtitle">Upload a lecture video for AI-powered chaptering and summarization</div>
          </div>
        </div>

        <div
          className={`file-drop-zone${selectedFile ? ' has-file' : ''}`}
          onClick={() => fileRef.current?.click()}
        >
          <div className="file-drop-icon">{selectedFile ? '✅' : '📁'}</div>
          <div className="file-drop-text">
            {selectedFile ? (
              <>Selected: <strong>{selectedFile.name}</strong> ({(selectedFile.size / (1024 * 1024)).toFixed(1)} MB)</>
            ) : (
              <>Click to select a video file<br /><span className="file-drop-hint">MP4, MKV, MOV, AVI, WEBM supported</span></>
            )}
          </div>
          <input
            ref={fileRef}
            type="file"
            accept=".mp4,.mkv,.mov,.avi,.webm,.flv,.m4v,.mpeg"
            onChange={handleFileSelect}
            style={{ display: 'none' }}
          />
        </div>

        <div style={{ marginTop: '1rem', display: 'flex', gap: '0.5rem' }}>
          <button className="btn btn-primary" onClick={handleUpload} disabled={isUploading || !selectedFile}>
            {isUploading ? 'Uploading...' : 'Upload & Process'}
          </button>
          {selectedFile && !isUploading && (
            <button className="btn btn-secondary" onClick={() => { setSelectedFile(null); if (fileRef.current) fileRef.current.value = ''; }}>
              Clear
            </button>
          )}
        </div>

        {isUploading && uploadProgress > 0 && (
          <div className="progress-container">
            <div className="progress-bar-track">
              <div className="progress-bar-fill" style={{ width: `${uploadProgress}%` }} />
            </div>
            <div className="progress-text">{uploadProgress}%</div>
          </div>
        )}

        {status && <div className={`status-msg ${status.type}`}>{status.text}</div>}
      </div>

      {/* Processing Status Card */}
      {jobId && (
        <div className="card">
          <div className="card-header">
            <div>
              <div className="card-title">Processing Status</div>
              <div className="card-subtitle">Job: {jobId.slice(0, 8)}...</div>
            </div>
            <div style={{ display: 'flex', gap: '0.5rem' }}>
              <button className="btn btn-secondary btn-sm" onClick={handleViewLog}>
                {showLog ? 'Hide Log' : 'View Log'}
              </button>
              {jobStatus === 'completed' && (
                <button className="btn btn-primary btn-sm" onClick={handleViewResults}>
                  View Results
                </button>
              )}
            </div>
          </div>

          <div className={`status-msg ${jobStatus === 'completed' ? 'success' : jobStatus === 'failed' ? 'error' : 'info'}`}>
            {jobStatus === 'processing' && <div className="spinner" />}
            {jobProgress}
          </div>

          {showLog && logContent && (
            <div className="log-viewer">{logContent}</div>
          )}
        </div>
      )}
    </>
  );
}
