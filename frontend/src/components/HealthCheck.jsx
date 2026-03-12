import { useState } from 'react'
import { styles } from '../styles'

export default function HealthCheck({ apiBase }) {
  const [health, setHealth] = useState(null)
  const [loading, setLoading] = useState(false)

  const checkHealth = async () => {
    setLoading(true)
    try {
      const res = await fetch(`${apiBase}/api/health`)
      const data = await res.json()
      setHealth(data)
    } catch (e) {
      setHealth({ error: e.message })
    } finally {
      setLoading(false)
    }
  }

  const getStatusDisplay = (status) => {
    if (status === 'ready' || status === 'healthy') {
      return { dot: 'green', text: status }
    }
    return { dot: 'red', text: status || 'unknown' }
  }

  return (
    <div style={styles.card}>
      <h2 style={styles.cardHeading}>Service Health</h2>
      <button 
        onClick={checkHealth} 
        disabled={loading}
        style={{
          ...styles.button,
          ...(loading && styles.buttonDisabled)
        }}
      >
        {loading ? 'Checking...' : 'Check Status'}
      </button>
      {health && !health.error && (
        <div>
          <HealthRow label="StudyBuzz App" status={health.status} />
          <HealthRow label="Mistral LLM (port 8000)" status={health.mistral} />
          <HealthRow label="Whisper STT (port 8001)" status={health.whisper} />
          <HealthRow label="Nemotron Embeddings (port 8002)" status={health.nemotron} />
          {health.mistral === 'ready' && health.whisper === 'ready' && health.nemotron === 'ready' && (
            <div style={{ ...styles.status, ...styles.statusSuccess, marginTop: '0.5rem' }}>
              All models loaded. Ready to process videos.
            </div>
          )}
        </div>
      )}
      {health?.error && (
        <div style={{ ...styles.status, ...styles.statusError }}>
          Error checking health: {health.error}
        </div>
      )}
    </div>
  )
}

function HealthRow({ label, status }) {
  const statusInfo = getStatusDisplay(status)
  
  return (
    <div style={styles.healthRow}>
      <span 
        style={{
          ...styles.dot,
          ...(statusInfo.dot === 'green' ? styles.dotGreen : styles.dotRed)
        }}
      ></span>
      <span>{statusInfo.text}</span> — <span>{label}</span>
    </div>
  )
}

function getStatusDisplay(status) {
  if (status === 'ready' || status === 'healthy') {
    return { dot: 'green', text: status }
  }
  return { dot: 'red', text: status || 'unknown' }
}