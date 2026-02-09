import React, { useState } from 'react';
import {
  Container,
  Box,
  Grid,
  AppBar,
  Toolbar,
  Typography,
  Button,
  ThemeProvider,
  createTheme
} from '@mui/material';
import VideoLibraryIcon from '@mui/icons-material/VideoLibrary';
import VideoUploader from './components/VideoUploader';
import ProcessingStatus from './components/ProcessingStatus';
import VideoPlayer from './components/VideoPlayer';
import ChapterMarkers from './components/ChapterMarkers';
import SummaryPanel from './components/SummaryPanel';
import './App.css';


const gtTheme = createTheme({
  palette: {
    primary: {
      main: '#003057',
      light: '#13294B',
      dark: '#001F3F',
      contrastText: '#FFFFFF'
    },
    secondary: {
      main: '#EAAA00',
      light: '#B3A369',
      dark: '#B8860B',
      contrastText: '#003057'
    },
    background: {
      default: '#F5F5F5',
      paper: '#FFFFFF'
    }
  },
  typography: {
    fontFamily: [
      '-apple-system',
      'BlinkMacSystemFont',
      '"Segoe UI"',
      'Roboto',
      '"Helvetica Neue"',
      'Arial',
      'sans-serif'
    ].join(','),
    h6: {
      fontWeight: 600
    }
  }
});

function App() {
  const [appState, setAppState] = useState('upload');
  const [jobId, setJobId] = useState(null);
  const [results, setResults] = useState(null);
  const [currentVideoTime, setCurrentVideoTime] = useState(0);
  const [seekToTime, setSeekToTime] = useState(null);

  const handleUploadComplete = uploadData => {
    setJobId(uploadData.job_id);
    setAppState('processing');
  };

  const handleProcessingComplete = async completedJobId => {
    try {
      const api = await import('./services/api');
      const resultsData = await api.getResults(completedJobId);
      setResults(resultsData);
      setJobId(completedJobId);
      setAppState('viewing');
    } catch (error) {
      console.error('Failed to fetch results:', error);
      alert('Failed to load results. Please try again.');
    }
  };

  const handleProcessingError = error => {
    console.error('Processing error:', error);
    alert(`Processing failed: ${error}`);
    setAppState('upload');
    setJobId(null);
  };

  const handleStartOver = () => {
    setAppState('upload');
    setJobId(null);
    setResults(null);
    setCurrentVideoTime(0);
    setSeekToTime(null);
  };

  const handleSeek = time => {
    setSeekToTime(time);
  };

  const handleVideoTimeUpdate = time => {
    setCurrentVideoTime(time);
    if (seekToTime !== null) {
      setSeekToTime(null);
    }
  };

  return (
    <ThemeProvider theme={gtTheme}>
      <Box
        sx={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}
      >
        <AppBar
          position='static'
          elevation={3}
          sx={{ bgcolor: 'primary.main' }}
        >
          <Toolbar>
            <VideoLibraryIcon sx={{ mr: 2 }} />
            <Typography variant='h6' component='div' sx={{ flexGrow: 1 }}>
              Video Lecture Summarizer
            </Typography>
            {appState !== 'upload' && (
              <Button
                sx={{
                  color: 'secondary.main',
                  '&:hover': {
                    backgroundColor: 'rgba(234, 170, 0, 0.1)'
                  }
                }}
                onClick={handleStartOver}
              >
                Upload New Video
              </Button>
            )}
          </Toolbar>
        </AppBar>

        {/* Main Content */}
        <Box sx={{ flex: 1, bgcolor: 'background.default', py: 3 }}>
          <Container maxWidth='xl'>
            {appState === 'upload' && (
              <VideoUploader onUploadComplete={handleUploadComplete} />
            )}

            {appState === 'processing' && jobId && (
              <ProcessingStatus
                jobId={jobId}
                onProcessingComplete={handleProcessingComplete}
                onProcessingError={handleProcessingError}
              />
            )}

            {appState === 'viewing' && results && jobId && (
              <Grid container spacing={3}>
                <Grid item xs={12} md={8}>
                  {/* Video Player */}
                  <Box sx={{ mb: 3 }}>
                    <VideoPlayer
                      videoUrl={`./api/video/${jobId}`}
                      onTimeUpdate={handleVideoTimeUpdate}
                      seekToTime={seekToTime}
                    />
                  </Box>

                  {/* AI Summary */}
                  <SummaryPanel
                    summary={results.summary}
                    timestamps={results.timestamps}
                  />
                </Grid>

                {/* Sidebar - Chapters Only */}
                <Grid item xs={12} md={4}>
                  <Box sx={{ position: 'sticky', top: 24 }}>
                    <ChapterMarkers
                      timestamps={results.timestamps}
                      currentTime={currentVideoTime}
                      onSeek={handleSeek}
                    />
                  </Box>
                </Grid>
              </Grid>
            )}
          </Container>
        </Box>
        <Box
          component='footer'
          sx={{
            py: 2.5,
            px: 2,
            mt: 'auto',
            background: 'linear-gradient(135deg, #003057 0%, #13294B 100%)',
            textAlign: 'center',
            borderTop: '3px solid #EAAA00'
          }}
        >
          <Typography
            variant='body2'
            sx={{
              color: '#FFFFFF',
              fontWeight: 500
            }}
          >
            Video Lecture Summarizer • Powered by the Georgia Tech AI Makerspace
          </Typography>
        </Box>
      </Box>
    </ThemeProvider>
  );
}

export default App;