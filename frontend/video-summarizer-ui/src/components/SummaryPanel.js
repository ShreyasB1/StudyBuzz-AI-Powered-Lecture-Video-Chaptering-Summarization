import React from 'react';
import {
  Box,
  Paper,
  Typography,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Chip
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import SummarizeIcon from '@mui/icons-material/Summarize';

const SummaryPanel = ({ summary, timestamps }) => {
  // Combine summary with timestamps for display
  const getSummaryData = () => {
    if (!summary || !Array.isArray(summary)) return [];

    return summary.map((item, index) => {
      // Each item in summary is like: { "00:00:00": { "Introduction": "summary text" } }
      const timeKey = Object.keys(item)[0];
      const chapterData = item[timeKey];
      const chapterTitle = Object.keys(chapterData)[0];
      const summaryText = chapterData[chapterTitle];

      return {
        time: timeKey,
        title: chapterTitle,
        summary: summaryText,
        index: index
      };
    });
  };

  const summaryData = getSummaryData();

  return (
    <Paper
      elevation={3}
      sx={{display: 'flex', flexDirection: 'column' }}
    >
      <Box sx={{ p: 2, borderBottom: 1, borderColor: 'divider' }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <SummarizeIcon color='primary' />
          <Typography variant='h6'>AI Summary</Typography>
        </Box>
        <Typography variant='caption' color='text.secondary'>
          AI-generated summaries for each chapter
        </Typography>
      </Box>

      <Box
        sx={{
          flex: 1,
          overflow: 'auto',
          p: 2
        }}
      >
        {summaryData.length === 0 ? (
          <Typography color='text.secondary' align='center' sx={{ mt: 4 }}>
            No summaries available
          </Typography>
        ) : (
          <Box>
            {summaryData.map((item, index) => (
              <Accordion
                key={index}
                defaultExpanded={index === 0}
                sx={{
                  mb: 2,
                  '&:before': {
                    display: 'none'
                  }
                }}
              >
                <AccordionSummary
                  expandIcon={<ExpandMoreIcon />}
                  sx={{
                    backgroundColor: 'grey.100',
                    borderRadius: 1,
                    '&:hover': {
                      backgroundColor: 'grey.200'
                    }
                  }}
                >
                  <Box sx={{ width: '100%', pr: 2 }}>
                    <Box
                      sx={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 1,
                        mb: 0.5,
                        flexWrap: 'wrap'
                      }}
                    >
                      <Chip
                        label={item.time}
                        size='small'
                        color='primary'
                        sx={{ height: 20, fontSize: '0.7rem' }}
                      />
                      <Typography
                        variant='subtitle2'
                        sx={{ fontWeight: 'bold' }}
                      >
                        Chapter {index + 1}
                      </Typography>
                    </Box>
                    <Typography
                      variant='body2'
                      sx={{
                        wordWrap: 'break-word',
                        overflowWrap: 'break-word'
                      }}
                    >
                      {item.title}
                    </Typography>
                  </Box>
                </AccordionSummary>
                <AccordionDetails sx={{ pt: 2 }}>
                  <Typography
                    variant='body2'
                    color='text.secondary'
                    sx={{
                      lineHeight: 1.7,
                      wordWrap: 'break-word',
                      overflowWrap: 'break-word',
                      whiteSpace: 'pre-wrap'
                    }}
                  >
                    {item.summary}
                  </Typography>
                </AccordionDetails>
              </Accordion>
            ))}
          </Box>
        )}
      </Box>
    </Paper>
  );
};

export default SummaryPanel;
