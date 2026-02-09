import React from 'react';
import {
  Box,
  Paper,
  Typography,
  List,
  ListItem,
  ListItemButton,
  ListItemText,
  Chip
} from '@mui/material';
import PlayCircleOutlineIcon from '@mui/icons-material/PlayCircleOutline';

const ChapterMarkers = ({ timestamps, currentTime, onSeek }) => {
  const parseTimestamp = timeStr => {
    // Parse timestamp format: HH:MM:SS or MM:SS
    const parts = timeStr.split(':');
    let seconds = 0;

    if (parts.length === 3) {
      seconds =
        parseInt(parts[0]) * 3600 +
        parseInt(parts[1]) * 60 +
        parseInt(parts[2]);
    } else if (parts.length === 2) {
      seconds = parseInt(parts[0]) * 60 + parseInt(parts[1]);
    }

    return seconds;
  };

  const isActiveChapter = (startTime, nextStartTime) => {
    const start = parseTimestamp(startTime);
    const end = nextStartTime ? parseTimestamp(nextStartTime) : Infinity;
    return currentTime >= start && currentTime < end;
  };

  const handleChapterClick = timeStr => {
    if (onSeek) {
      const seconds = parseTimestamp(timeStr);
      onSeek(seconds);
    }
  };

  return (
    <Paper
      elevation={3}
      sx={{display: 'flex', flexDirection: 'column' }}
    >
      <Box sx={{ p: 2, borderBottom: 1, borderColor: 'divider' }}>
        <Typography variant='h6'>Chapters</Typography>
        <Typography variant='caption' color='text.secondary'>
          {timestamps?.length || 0} chapters
        </Typography>
      </Box>

      <Box
        sx={{
          flex: 1,
          overflow: 'auto',
          p: 1
        }}
      >
        {!timestamps || timestamps.length === 0 ? (
          <Typography color='text.secondary' align='center' sx={{ mt: 4 }}>
            No chapters available
          </Typography>
        ) : (
          <List>
            {timestamps.map((chapter, index) => {
              const nextChapterTime =
                index < timestamps.length - 1
                  ? timestamps[index + 1].time
                  : null;
              const isActive = isActiveChapter(chapter.time, nextChapterTime);

              return (
                <ListItem key={index} disablePadding sx={{ mb: 1 }}>
                  <ListItemButton
                    onClick={() => handleChapterClick(chapter.time)}
                    sx={{
                      borderRadius: 1,
                      border: 1,
                      borderColor: isActive ? 'primary.main' : 'divider',
                      backgroundColor: isActive
                        ? 'primary.light'
                        : 'transparent',
                      '&:hover': {
                        backgroundColor: isActive
                          ? 'primary.light'
                          : 'action.hover'
                      },
                      transition: 'all 0.2s'
                    }}
                  >
                    <PlayCircleOutlineIcon
                      sx={{
                        mr: 2,
                        color: isActive ? 'primary.main' : 'action.active'
                      }}
                    />
                    <ListItemText
                      primary={
                        <Box
                          sx={{ display: 'flex', alignItems: 'center', gap: 1 }}
                        >
                          <Typography
                            variant='body2'
                            sx={{
                              fontWeight: isActive ? 'bold' : 'normal',
                              color: isActive
                                ? 'primary.contrastText'
                                : 'text.primary',
                              flex: 1
                            }}
                          >
                            {chapter.title}
                          </Typography>
                        </Box>
                      }
                      secondary={
                        <Chip
                          label={chapter.time}
                          size='small'
                          sx={{
                            mt: 0.5,
                            height: 20,
                            fontSize: '0.7rem',
                            backgroundColor: isActive
                              ? 'primary.main'
                              : 'default',
                            color: isActive
                              ? 'primary.contrastText'
                              : 'text.secondary'
                          }}
                        />
                      }
                    />
                  </ListItemButton>
                </ListItem>
              );
            })}
          </List>
        )}
      </Box>
    </Paper>
  );
};

export default ChapterMarkers;
