import React, { useEffect, useState } from 'react';
import {
  Box,
  Typography,
  Paper,
  LinearProgress,
  Alert,
  Stepper,
  Step,
  StepLabel,
  CircularProgress
} from '@mui/material';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import ErrorIcon from '@mui/icons-material/Error';

const ProcessingStatus = ({
  jobId,
  onProcessingComplete,
  onProcessingError
}) => {
  const [status, setStatus] = useState(null);
  const [error, setError] = useState(null);
  const [simulatedStep, setSimulatedStep] = useState(0); // visual progression

  const steps = [
    'Video Uploaded',
    'Converting Audio',
    'Transcribing Speech',
    'Generating Chapters',
    'Analyzing Content',
    'Creating Summary'
  ];

  // simulating progress visually by advance step every 10 seconds
  useEffect(() => {
    const progressTimer = setInterval(() => {
      setSimulatedStep(prev => {
        // Don't go past step 5 (index 4) - save last step for actual completion
        if (prev < 4) {
          return prev + 1;
        }
        return prev;
      });
    }, 10000); // 10 seconds

    return () => clearInterval(progressTimer);
  }, []);

  // Poll backend for actual status
  useEffect(() => {
    let cancelled = false;
    let pollInterval;

    const pollStatus = async () => {
      try {
        const api = await import('../services/api');
        const statusData = await api.checkStatus(jobId);

        if (cancelled) return;

        setStatus(statusData);

        if (statusData.status === 'completed') {
          clearInterval(pollInterval);
          setSimulatedStep(6); // Jump to completion
          if (onProcessingComplete) {
            onProcessingComplete(jobId);
          }
        } else if (statusData.status === 'failed') {
          clearInterval(pollInterval);
          setError(statusData.error || 'Processing failed');
          if (onProcessingError) {
            onProcessingError(statusData.error || 'Processing failed');
          }
        }
      } catch (err) {
        if (cancelled) return;
        console.error('Status polling error:', err);
        setError('Failed to check processing status');
        clearInterval(pollInterval);
        if (onProcessingError) {
          onProcessingError('Failed to check processing status');
        }
      }
    };

    // Initial poll
    pollStatus();

    // Poll every 2 seconds
    pollInterval = setInterval(pollStatus, 2000);

    return () => {
      cancelled = true;
      clearInterval(pollInterval);
    };
  }, [jobId, onProcessingComplete, onProcessingError]);

  const activeStep = simulatedStep;
  const isCompleted = status?.status === 'completed';
  const isFailed = status?.status === 'failed';

  return (
    <Box sx={{ width: '100%', maxWidth: 800, mx: 'auto', p: 3 }}>
      <Paper elevation={3} sx={{ p: 4 }}>
        <Box sx={{ textAlign: 'center', mb: 4 }}>
          {isCompleted ? (
            <>
              <CheckCircleIcon
                sx={{ fontSize: 64, color: 'success.main', mb: 2 }}
              />
              <Typography variant='h5' color='success.main' gutterBottom>
                Processing Complete!
              </Typography>
              <Typography variant='body2' color='text.secondary'>
                Your video has been analyzed and is ready to view
              </Typography>
            </>
          ) : isFailed ? (
            <>
              <ErrorIcon sx={{ fontSize: 64, color: 'error.main', mb: 2 }} />
              <Typography variant='h5' color='error.main' gutterBottom>
                Processing Failed
              </Typography>
              <Typography variant='body2' color='text.secondary'>
                {error || 'An error occurred during processing'}
              </Typography>
            </>
          ) : (
            <>
              <CircularProgress size={64} sx={{ mb: 2 }} />
              <Typography variant='h5' gutterBottom>
                Processing Video...
              </Typography>
              <Typography variant='body2' color='text.secondary'>
                {steps[activeStep] || 'Please wait while we analyze your video'}
              </Typography>
            </>
          )}
        </Box>

        {!isFailed && (
          <Box sx={{ width: '100%', mt: 4 }}>
            <Stepper activeStep={activeStep} alternativeLabel>
              {steps.map((label, index) => (
                <Step key={label} completed={index < activeStep || isCompleted}>
                  <StepLabel>{label}</StepLabel>
                </Step>
              ))}
            </Stepper>
          </Box>
        )}

        {status?.filename && (
          <Box sx={{ mt: 3, p: 2, bgcolor: 'grey.100', borderRadius: 1 }}>
            <Typography variant='caption' color='text.secondary'>
              File: {status.filename}
            </Typography>
          </Box>
        )}

        {!isCompleted && !isFailed && (
          <Box sx={{ width: '100%', mt: 3 }}>
            <LinearProgress />
            <Typography
              variant='caption'
              color='text.secondary'
              sx={{ mt: 1, display: 'block', textAlign: 'center' }}
            >
              This may take several minutes for long videos...
            </Typography>
          </Box>
        )}

        {error && (
          <Alert severity='error' sx={{ mt: 3 }}>
            {error}
          </Alert>
        )}
      </Paper>

      <Box sx={{ mt: 2, textAlign: 'center' }}>
        <Typography variant='caption' color='text.secondary'>
          Job ID: {jobId}
        </Typography>
      </Box>
    </Box>
  );
};

export default ProcessingStatus;
