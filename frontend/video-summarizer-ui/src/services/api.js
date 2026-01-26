// API Client for Video Summarizer
// Uses relative paths since frontend and backend are served from the same origin (Flask serves both)

import axios from 'axios';

const API_BASE_URL = './api';

/**
 * Upload a video file for processing
 * @param {File} file - Video file to upload
 * @param {Function} onProgress - Callback for upload progress (0-100)
 * @returns {Promise<Object>} Response with job_id
 */
export const uploadVideo = async (file, onProgress) => {
  const formData = new FormData();
  formData.append('video', file);

  const config = {
    headers: {
      'Content-Type': 'multipart/form-data'
    },
    onUploadProgress: progressEvent => {
      if (onProgress && progressEvent.total) {
        const percentCompleted = Math.round(
          (progressEvent.loaded * 100) / progressEvent.total
        );
        onProgress(percentCompleted);
      }
    }
  };

  const response = await axios.post(`${API_BASE_URL}/upload`, formData, config);
  return response.data;
};

/**
 * Check the status of a processing job
 * @param {string} jobId - Job ID from upload
 * @returns {Promise<Object>} Job status object
 */
export const checkStatus = async jobId => {
  const response = await axios.get(`${API_BASE_URL}/status/${jobId}`);
  return response.data;
};

/**
 * Get all results for a completed job
 * @param {string} jobId - Job ID from upload
 * @returns {Promise<Object>} Results including transcript, timestamps, summary
 */
export const getResults = async jobId => {
  const response = await axios.get(`${API_BASE_URL}/results/${jobId}`);
  return response.data;
};

/**
 * Get video URL for playback
 * @param {string} jobId - Job ID from upload
 * @returns {string} Video stream URL
 */
export const getVideoUrl = jobId => {
  return `${API_BASE_URL}/video/${jobId}`;
};

/**
 * Health check
 * @returns {Promise<Object>} Health status
 */
export const healthCheck = async () => {
  const response = await axios.get(`${API_BASE_URL}/health`);
  return response.data;
};

/**
 * List all jobs (for debugging)
 * @returns {Promise<Object>} All jobs
 */
export const listJobs = async () => {
  const response = await axios.get(`${API_BASE_URL}/jobs`);
  return response.data;
};
