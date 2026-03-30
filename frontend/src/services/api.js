const API_BASE = '/api';

async function request(url, options = {}) {
  const res = await fetch(url, options);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data?.error || `Request failed (HTTP ${res.status})`);
  }
  return data;
}

export async function checkHealth() {
  return request(`${API_BASE}/health`);
}

export async function getGpuStatus() {
  return request(`${API_BASE}/gpu-status`);
}

export async function uploadVideo(file, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', `${API_BASE}/upload`);

    xhr.upload.onprogress = (evt) => {
      if (evt.lengthComputable && onProgress) {
        onProgress(Math.round((evt.loaded / evt.total) * 100));
      }
    };

    xhr.onload = () => {
      const contentType = xhr.getResponseHeader('content-type') || '';
      const isJson = contentType.includes('application/json');
      const body = isJson ? JSON.parse(xhr.responseText || '{}') : { raw: xhr.responseText };
      if (xhr.status >= 200 && xhr.status < 300) resolve(body);
      else reject(new Error(body?.error || `Upload failed (HTTP ${xhr.status})`));
    };

    xhr.onerror = () => reject(new Error('Network error'));

    const formData = new FormData();
    formData.append('file', file);
    xhr.send(formData);
  });
}

export async function getJobStatus(jobId) {
  return request(`${API_BASE}/status/${encodeURIComponent(jobId)}`);
}

export async function getJobResults(jobId) {
  return request(`${API_BASE}/results/${encodeURIComponent(jobId)}`);
}

export async function getResultsByHash(videoHash) {
  return request(`${API_BASE}/results/hash/${encodeURIComponent(videoHash)}`);
}

export async function getPipelineLog(jobId) {
  return request(`${API_BASE}/log/${encodeURIComponent(jobId)}`);
}

export async function listJobs() {
  return request(`${API_BASE}/jobs`);
}

export async function listVideos() {
  return request(`${API_BASE}/videos`);
}

export async function searchVideos(query) {
  const url = new URL(`${API_BASE}/search`, window.location.origin);
  url.searchParams.set('q', query);
  return request(url.toString());
}

export function getVideoStreamUrl(jobId) {
  return `${API_BASE}/video/${encodeURIComponent(jobId)}`;
}

export function getVideoStreamUrlByHash(videoHash) {
  return `${API_BASE}/video/hash/${encodeURIComponent(videoHash)}`;
}

export async function createChatStream(message, rag) {
  const url = `${API_BASE}/chat`;
  return fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, rag }),
  });
}
