import { useState, useEffect } from 'react'
import { styles } from '../styles'

export default function ProcessingStatus({ jobId, apiBase, onComplete }) {
  const [status, setStatus] = useState('Processing...')
  const [pollTimer, setPollTimer] = useState(null)

  useEffect(() => {
    if (!jobId) return

    const pollStatus = async () => {
      try {
        const res = await fetch(`${apiBase}/api/status/${jobId}`)
        const data = await res.json()

        if (data.status === 'completed') {
          setStatus('Processing complete!')
          if (pollTimer) clearInterval(pollTimer)
          onComplete(data)
        } else if (data.status === 'failed') {
          setStatus(`Processing failed: ${data.error || 'Unknown error'}`)
          if (pollTimer) clearInterval(pollTimer)
        } else {
          setStatus(data.progress || data.status || 'Processing...')
        }
      } catch (e) {
        setStatus(`Polling error: ${e.message}`)
      }
    }

    if (!pollTimer) {
      pollStatus()
      const timer = setInterval(pollStatus, 3000)
      setPollTimer(timer)
    }

    return () => {
      if (pollTimer) clearInterval(pollTimer)
    }
  }, [jobId, apiBase, onComplete, pollTimer])

  return (
    <div style={styles.card}>
      <h2 style={styles.cardHeading}>Processing Status</h2>
      <div style={{ ...styles.status, ...styles.statusInfo }}>
        {status}
      </div>
    </div>
  )
}