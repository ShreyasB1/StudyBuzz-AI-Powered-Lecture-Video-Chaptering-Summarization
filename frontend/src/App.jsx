import React, { useState } from 'react';
import Navbar from './components/Navbar.jsx';
import DashboardPanel from './components/DashboardPanel.jsx';
import UploadPanel from './components/UploadPanel.jsx';
import LibraryPanel from './components/LibraryPanel.jsx';
import SearchPanel from './components/SearchPanel.jsx';
import VideoResultsView from './components/VideoResultsView.jsx';
import ChatPanel from './components/ChatPanel.jsx';

const TABS = [
  { id: 'dashboard', label: 'Dashboard' },
  { id: 'upload', label: 'Upload' },
  { id: 'library', label: 'Library' },
  { id: 'search', label: 'Search' },
  { id: 'chat', label: 'Chat' },
];

export default function App() {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [viewingVideo, setViewingVideo] = useState(null);

  function handleViewVideo(video) {
    setViewingVideo(video);
  }

  function handleBack() {
    setViewingVideo(null);
  }

  return (
    <div className="app">
      <Navbar
        tabs={TABS}
        activeTab={activeTab}
        onTabChange={(id) => { setActiveTab(id); setViewingVideo(null); }}
      />
      <main className="main-content">
        {viewingVideo ? (
          <VideoResultsView video={viewingVideo} onBack={handleBack} />
        ) : (
          <>
            {activeTab === 'dashboard' && <DashboardPanel />}
            {activeTab === 'upload' && <UploadPanel onViewResults={handleViewVideo} />}
            {activeTab === 'library' && <LibraryPanel onViewVideo={handleViewVideo} />}
            {activeTab === 'search' && <SearchPanel onViewVideo={handleViewVideo} />}
            {activeTab === 'chat' && <ChatPanel />}
          </>
        )}
      </main>
    </div>
  );
}

