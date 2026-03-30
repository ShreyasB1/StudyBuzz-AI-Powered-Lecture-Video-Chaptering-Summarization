# StudyBuzz Frontend - React

A modern React-based frontend for the StudyBuzz video processing application, built with Vite and styled entirely with React inline styles.

## Features

- **Health Check**: Monitor the status of all backend services (StudyBuzz app, Mistral LLM, Whisper STT, Nemotron Embeddings)
- **Video Upload**: Upload lecture videos in multiple formats (MP4, MKV, MOV, AVI, WEBM, FLV, M4V, MPEG)
- **Processing Status**: Real-time polling to track video processing progress
- **Log Viewer**: View detailed pipeline logs for processing jobs
- **Results Display**: Display chapters, summaries, and transcripts from processed videos

## Architecture

- **Pure React Components**: All components are functional components using React hooks
- **Inline Styling**: All styles are defined in `src/styles.js` - no CSS files
- **API Integration**: Communicates with backend via REST API endpoints
- **State Management**: Uses React hooks (useState, useEffect) for state management

### Components

- `HealthCheck.jsx` - Service health monitoring
- `VideoUpload.jsx` - File upload functionality
- `ProcessingStatus.jsx` - Real-time processing status with polling
- `LogViewer.jsx` - Pipeline log display
- `Results.jsx` - Results visualization (chapters, summaries, transcripts)
- `styles.js` - Centralized style definitions

## Installation

```bash
npm install
```

## Development

Start the development server:

```bash
npm run dev
```

The frontend will be available at `http://localhost:3000` with API proxy configured for `http://localhost:5000`.

## Building

Create an optimized production build:

```bash
npm run build
```

Preview the production build:

```bash
npm run preview
```

## API Integration

The frontend connects to the following backend endpoints:

- `GET /api/health` - Check service health
- `POST /api/upload` - Upload video file
- `GET /api/status/{jobId}` - Get processing status
- `GET /api/log/{jobId}` - Get processing logs
- `GET /api/results/{jobId}` - Get processing results

## Style System

All styling is defined in `src/styles.js` and imported into components:

```javascript
import { styles } from '../styles'

// Usage in components
<div style={styles.card}>
  <h2 style={styles.cardHeading}>Title</h2>
</div>
```

## Responsive Design

The styles use a mobile-first approach with:
- Max width container (800px)
- Flexible padding and margins
- Responsive font sizes
- Touch-friendly button sizes

## Color Scheme

- Primary Blue: `#003057`
- Success Green: `#137333`
- Error Red: `#c5221f`
- Warning Yellow: `#7c5e00`
- Light Gray: `#f5f5f5`
- Dark Gray: `#1e1e1e`
