import React, { useRef, useState, useEffect } from 'react';
import { Box, Paper, IconButton, Slider, Typography } from '@mui/material';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import PauseIcon from '@mui/icons-material/Pause';
import VolumeUpIcon from '@mui/icons-material/VolumeUp';
import VolumeOffIcon from '@mui/icons-material/VolumeOff';
import FullscreenIcon from '@mui/icons-material/Fullscreen';

const VideoPlayer = ({ videoUrl, onTimeUpdate, seekToTime }) => {
  const videoRef = useRef(null);
  const containerRef = useRef(null);
  const [playing, setPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [volume, setVolume] = useState(1);
  const [muted, setMuted] = useState(false);

  // Handle external seek requests
  useEffect(() => {
    if (seekToTime !== null && seekToTime !== undefined && videoRef.current) {
      videoRef.current.currentTime = seekToTime;
      if (onTimeUpdate) {
        onTimeUpdate(seekToTime);
      }
    }
  }, [seekToTime, onTimeUpdate]);

  const togglePlay = () => {
    if (videoRef.current) {
      if (playing) {
        videoRef.current.pause();
      } else {
        videoRef.current.play();
      }
      setPlaying(!playing);
    }
  };

  const handleTimeUpdate = () => {
    if (videoRef.current) {
      setCurrentTime(videoRef.current.currentTime);
      if (onTimeUpdate) {
        onTimeUpdate(videoRef.current.currentTime);
      }
    }
  };

  const handleLoadedMetadata = () => {
    if (videoRef.current) {
      setDuration(videoRef.current.duration);
    }
  };

  const handleSeek = (event, newValue) => {
    if (videoRef.current) {
      videoRef.current.currentTime = newValue;
      setCurrentTime(newValue);
      if (onTimeUpdate) {
        onTimeUpdate(newValue);
      }
    }
  };

  const handleVolumeChange = (event, newValue) => {
    if (videoRef.current) {
      videoRef.current.volume = newValue;
      setVolume(newValue);
      setMuted(newValue === 0);
    }
  };

  const toggleMute = () => {
    if (videoRef.current) {
      videoRef.current.muted = !muted;
      setMuted(!muted);
    }
  };

  const toggleFullscreen = () => {
    if (containerRef.current) {
      if (!document.fullscreenElement) {
        containerRef.current.requestFullscreen();
      } else {
        document.exitFullscreen();
      }
    }
  };

  const formatTime = seconds => {
    if (!seconds || isNaN(seconds)) return '0:00';
    const hrs = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);

    if (hrs > 0) {
      return `${hrs}:${mins.toString().padStart(2, '0')}:${secs
        .toString()
        .padStart(2, '0')}`;
    }
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  return (
    <Paper elevation={3} ref={containerRef}>
      <Box sx={{ position: 'relative', backgroundColor: '#000' }}>
        <video
          ref={videoRef}
          src={videoUrl}
          onTimeUpdate={handleTimeUpdate}
          onLoadedMetadata={handleLoadedMetadata}
          onEnded={() => setPlaying(false)}
          style={{
            width: '100%',
            height: 'auto',
            display: 'block'
          }}
        />

        {/* Controls Overlay */}
        <Box
          sx={{
            position: 'absolute',
            bottom: 0,
            left: 0,
            right: 0,
            background: 'linear-gradient(transparent, rgba(0,0,0,0.8))',
            p: 2
          }}
        >
          {/* Progress Bar */}
          <Slider
            value={currentTime}
            max={duration}
            onChange={handleSeek}
            sx={{
              color: 'primary.main',
              '& .MuiSlider-thumb': {
                width: 12,
                height: 12
              }
            }}
          />

          {/* Time Display and Controls */}
          <Box
            sx={{
              display: 'flex',
              alignItems: 'center',
              gap: 1,
              mt: 1
            }}
          >
            {/* Play/Pause Button */}
            <IconButton onClick={togglePlay} sx={{ color: 'white' }}>
              {playing ? <PauseIcon /> : <PlayArrowIcon />}
            </IconButton>

            {/* Time */}
            <Typography variant='body2' sx={{ color: 'white', minWidth: 100 }}>
              {formatTime(currentTime)} / {formatTime(duration)}
            </Typography>

            {/* Volume Controls */}
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, ml: 2 }}>
              <IconButton onClick={toggleMute} sx={{ color: 'white' }}>
                {muted ? <VolumeOffIcon /> : <VolumeUpIcon />}
              </IconButton>
              <Slider
                value={muted ? 0 : volume}
                max={1}
                step={0.1}
                onChange={handleVolumeChange}
                sx={{
                  width: 100,
                  color: 'white',
                  '& .MuiSlider-thumb': {
                    width: 10,
                    height: 10
                  }
                }}
              />
            </Box>

            {/* Fullscreen Button */}
            <IconButton
              onClick={toggleFullscreen}
              sx={{ color: 'white', ml: 'auto' }}
            >
              <FullscreenIcon />
            </IconButton>
          </Box>
        </Box>
      </Box>
    </Paper>
  );
};

export default VideoPlayer;