import React from 'react';
import VideoUploadCard from './components/VideoUploadCard.jsx';
import VideoSearchCard from './components/VideoSearchCard.jsx';

export default function App() {
  return (
    <div className="container">
      <h1>StudyBuzz</h1>
      <p className="subtitle">AI-Powered Lecture Video Chaptering &amp; Summarization</p>

      {/* Keeping layout minimal and pixel-stable; existing static features can be re-added as needed */}
      <VideoUploadCard />
      <VideoSearchCard />
    </div>
  );
}

