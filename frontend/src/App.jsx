import { useState } from 'react'
import HealthCheck from './components/HealthCheck'
import VideoUpload from './components/VideoUpload'
import ProcessingStatus from './components/ProcessingStatus'
import LogViewer from './components/LogViewer'
import Results from './components/Results'
import Search from './components/Search'
import { styles } from './styles'

const API_BASE = window.location.pathname.replace(/\/$/, '')

export default function App() {
  const [jobId, setJobId] = useState(null)
  const [isProcessing, setIsProcessing] = useState(false)
  const [showResults, setShowResults] = useState(false)
  const [searchResults, setSearchResults] = useState(null)

  const handleUploadStart = (newJobId) => {
    setJobId(newJobId)
    setIsProcessing(true)
    setShowResults(false)
  }

  const handleProcessingComplete = () => {
    setIsProcessing(false)
    setShowResults(true)
  }

  const handleSearchResults = (data) => {
    setSearchResults(data)
  }

  return (
    <div style={styles.container}>
      <h1 style={styles.heading1}>StudyBuzz</h1>
      <p style={styles.subtitle}>AI-Powered Lecture Video Chaptering & Summarization</p>

      <HealthCheck apiBase={API_BASE} />
      <VideoUpload apiBase={API_BASE} onUploadStart={handleUploadStart} />

      {/* Search integration */}
      <Search apiBase={API_BASE} onResults={handleSearchResults} />
      {searchResults && (
        <div style={styles.card}>
          <h2 style={styles.cardHeading}>Search Results</h2>
          <pre style={styles.resultsPreview}>{JSON.stringify(searchResults, null, 2)}</pre>
        </div>
      )}

      {isProcessing && jobId && (
        <>
          <ProcessingStatus 
            jobId={jobId} 
            apiBase={API_BASE} 
            onComplete={handleProcessingComplete} 
          />
          <div style={styles.card}>
            <LogViewer jobId={jobId} apiBase={API_BASE} />
          </div>
        </>
      )}

      {jobId && <Results jobId={jobId} apiBase={API_BASE} show={showResults} />}
    </div>
  )
}
