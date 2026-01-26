import React, { useState, useEffect, useRef } from 'react';
import {
  Box,
  Paper,
  Typography,
  List,
  ListItem,
  ListItemText
} from '@mui/material';

const TranscriptPanel = ({ transcript, currentTime, onSeek }) => {
  const [entries, setEntries] = useState([]);
  const listRef = useRef(null);
  const activeItemRef = useRef(null);

  // Parse VTT transcript
  useEffect(() => {
    if (!transcript) return;

    const parseVTT = vttText => {
      const lines = vttText.split('\n');
      const parsedEntries = [];
      let currentEntry = null;

      for (let i = 0; i < lines.length; i++) {
        const line = lines[i].trim();

        // Skip WEBVTT header and empty lines
        if (!line || line.startsWith('WEBVTT')) continue;

        // Check if this is a timestamp line
        if (line.includes('-->')) {
          const [startStr, endStr] = line.split('-->').map(s => s.trim());
          const startTime = parseVTTTimestamp(startStr);
          const endTime = parseVTTTimestamp(endStr);

          currentEntry = {
            startTime,
            endTime,
            startStr,
            endStr,
            text: ''
          };
        } else if (currentEntry) {
          // This is text content
          if (line) {
            currentEntry.text += (currentEntry.text ? ' ' : '') + line;
          } else {
            // Empty line = end of entry
            if (currentEntry.text) {
              parsedEntries.push(currentEntry);
            }
            currentEntry = null;
          }
        }
      }

      // Add last entry if exists
      if (currentEntry && currentEntry.text) {
        parsedEntries.push(currentEntry);
      }

      return parsedEntries;
    };

    const parseVTTTimestamp = timestamp => {
      // Parse VTT timestamp format: HH:MM:SS.mmm or MM:SS.mmm
      const parts = timestamp.split(':');
      let seconds = 0;

      if (parts.length === 3) {
        // HH:MM:SS.mmm
        const hours = parseInt(parts[0]);
        const minutes = parseInt(parts[1]);
        const [secs, ms] = parts[2].split('.');
        seconds = hours * 3600 + minutes * 60 + parseInt(secs);
        if (ms) seconds += parseFloat('0.' + ms);
      } else if (parts.length === 2) {
        // MM:SS.mmm
        const minutes = parseInt(parts[0]);
        const [secs, ms] = parts[1].split('.');
        seconds = minutes * 60 + parseInt(secs);
        if (ms) seconds += parseFloat('0.' + ms);
      }

      return seconds;
    };

    const parsed = parseVTT(transcript);
    setEntries(parsed);
  }, [transcript]);

  // Auto-scroll to active entry
  useEffect(() => {
    if (activeItemRef.current && listRef.current) {
      activeItemRef.current.scrollIntoView({
        behavior: 'smooth',
        block: 'center'
      });
    }
  }, [currentTime]);

  const handleEntryClick = entry => {
    if (onSeek) {
      onSeek(entry.startTime);
    }
  };

  const isActive = entry => {
    return currentTime >= entry.startTime && currentTime < entry.endTime;
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
    <Paper
      elevation={3}
      sx={{display: 'flex', flexDirection: 'column' }}
    >
      <Box sx={{ p: 2, borderBottom: 1, borderColor: 'divider' }}>
        <Typography variant='h6'>Transcript</Typography>
        <Typography variant='caption' color='text.secondary'>
          Click any line to jump to that moment
        </Typography>
      </Box>

      <Box
        ref={listRef}
        sx={{
          flex: 1,
          overflow: 'auto',
          p: 2
        }}
      >
        {entries.length === 0 ? (
          <Typography color='text.secondary' align='center' sx={{ mt: 4 }}>
            No transcript available
          </Typography>
        ) : (
          <List>
            {entries.map((entry, index) => {
              const active = isActive(entry);
              return (
                <ListItem
                  key={index}
                  ref={active ? activeItemRef : null}
                  button
                  onClick={() => handleEntryClick(entry)}
                  sx={{
                    borderRadius: 1,
                    mb: 1,
                    backgroundColor: active ? 'primary.light' : 'transparent',
                    '&:hover': {
                      backgroundColor: active ? 'primary.light' : 'action.hover'
                    },
                    transition: 'background-color 0.2s'
                  }}
                >
                  <ListItemText
                    primary={
                      <Box
                        sx={{
                          display: 'flex',
                          alignItems: 'flex-start',
                          gap: 2
                        }}
                      >
                        <Typography
                          variant='caption'
                          sx={{
                            minWidth: 60,
                            color: active
                              ? 'primary.contrastText'
                              : 'text.secondary',
                            fontWeight: active ? 'bold' : 'normal'
                          }}
                        >
                          {formatTime(entry.startTime)}
                        </Typography>
                        <Typography
                          variant='body2'
                          sx={{
                            color: active
                              ? 'primary.contrastText'
                              : 'text.primary',
                            fontWeight: active ? 'bold' : 'normal'
                          }}
                        >
                          {entry.text}
                        </Typography>
                      </Box>
                    }
                  />
                </ListItem>
              );
            })}
          </List>
        )}
      </Box>
    </Paper>
  );
};

export default TranscriptPanel;
