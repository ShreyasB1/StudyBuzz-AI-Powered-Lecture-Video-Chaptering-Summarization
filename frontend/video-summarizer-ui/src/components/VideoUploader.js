import React, { useState, useRef } from 'react';
import {
  Box,
  Button,
  Typography,
  Paper,
  LinearProgress,
  Alert
} from '@mui/material';
import CloudUploadIcon from '@mui/icons-material/CloudUpload';
import VideoFileIcon from '@mui/icons-material/VideoFile';

const VideoUploader = ({ onUploadComplete }) => {
  const [selectedFile, setSelectedFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [error, setError] = useState(null);
  const [dragActive, setDragActive] = useState(false);
  const fileInputRef = useRef(null);

  const allowedTypes = [
    'video/mp4',
    'video/x-matroska',
    'video/quicktime',
    'video/x-msvideo',
    'video/webm',
    'video/x-flv',
    'video/mpeg'
  ];

  const handleFileSelect = file => {
    setError(null);

    if (!file) {
      return;
    }

    // Check file type
    if (
      !allowedTypes.includes(file.type) &&
      !file.name.match(/\.(mp4|mkv|mov|avi|webm|flv|m4v|mpeg)$/i)
    ) {
      setError('Invalid file type. Please upload a video file.');
      return;
    }

    // Check file size (limit to 2GB)
    const maxSize = 2 * 1024 * 1024 * 1024; // 2GB
    if (file.size > maxSize) {
      setError('File too large. Maximum size is 2GB.');
      return;
    }

    setSelectedFile(file);
  };

  const handleFileChange = event => {
    const file = event.target.files?.[0];
    handleFileSelect(file);
  };

  const handleDrag = e => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  };

  const handleDrop = e => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);

    const file = e.dataTransfer.files?.[0];
    handleFileSelect(file);
  };

  const handleUpload = async () => {
    if (!selectedFile) {
      return;
    }

    setUploading(true);
    setUploadProgress(0);
    setError(null);

    try {
      // Import API service dynamically
      const api = await import('../services/api');

      const result = await api.uploadVideo(selectedFile, progress => {
        setUploadProgress(progress);
      });

      // Notify parent component
      if (onUploadComplete) {
        onUploadComplete(result);
      }
    } catch (err) {
      console.error('Upload error:', err);
      setError(
        err.response?.data?.error || 'Failed to upload video. Please try again.'
      );
      setUploading(false);
    }
  };

  const formatFileSize = bytes => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + ' ' + sizes[i];
  };

  return (
    <Box sx={{ width: '100%', maxWidth: 800, mx: 'auto', p: 3 }}>
      <Typography variant='h4' gutterBottom align='center'>
        Video Summarizer
      </Typography>
      <Typography
        variant='body1'
        color='text.secondary'
        align='center'
        sx={{ mb: 4 }}
      >
        Upload a lecture video to generate transcripts, chapters, and AI
        summaries
      </Typography>

      <Paper
        elevation={3}
        sx={{
          p: 4,
          border: dragActive ? '2px dashed #1976d2' : '2px dashed #ccc',
          backgroundColor: dragActive ? 'action.hover' : 'background.paper',
          transition: 'all 0.3s ease'
        }}
        onDragEnter={handleDrag}
        onDragLeave={handleDrag}
        onDragOver={handleDrag}
        onDrop={handleDrop}
      >
        <Box
          sx={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: 2
          }}
        >
          {!selectedFile ? (
            <>
              <CloudUploadIcon sx={{ fontSize: 64, color: 'primary.main' }} />
              <Typography variant='h6'>
                Drag and drop a video file here
              </Typography>
              <Typography variant='body2' color='text.secondary'>
                or
              </Typography>
              <Button
                variant='contained'
                component='label'
                startIcon={<VideoFileIcon />}
                disabled={uploading}
              >
                Select Video File
                <input
                  type='file'
                  hidden
                  ref={fileInputRef}
                  accept='video/*'
                  onChange={handleFileChange}
                />
              </Button>
              <Typography variant='caption' color='text.secondary'>
                Supported formats: MP4, MKV, MOV, AVI, WEBM, MPEG (max 2GB)
              </Typography>
            </>
          ) : (
            <>
              <VideoFileIcon sx={{ fontSize: 64, color: 'success.main' }} />
              <Typography variant='h6'>{selectedFile.name}</Typography>
              <Typography variant='body2' color='text.secondary'>
                Size: {formatFileSize(selectedFile.size)}
              </Typography>

              {!uploading ? (
                <Box sx={{ display: 'flex', gap: 2, mt: 2 }}>
                  <Button
                    variant='contained'
                    color='primary'
                    size='large'
                    onClick={handleUpload}
                    startIcon={<CloudUploadIcon />}
                  >
                    Upload & Process
                  </Button>
                  <Button
                    variant='outlined'
                    size='large'
                    onClick={() => setSelectedFile(null)}
                  >
                    Change File
                  </Button>
                </Box>
              ) : (
                <Box sx={{ width: '100%', mt: 2 }}>
                  <Typography variant='body2' gutterBottom>
                    Uploading... {uploadProgress}%
                  </Typography>
                  <LinearProgress
                    variant='determinate'
                    value={uploadProgress}
                  />
                </Box>
              )}
            </>
          )}
        </Box>
      </Paper>

      {error && (
        <Alert severity='error' sx={{ mt: 2 }}>
          {error}
        </Alert>
      )}
    </Box>
  );
};

export default VideoUploader;
