import { useState } from 'react'
import { styles } from '../styles'

export default function LogViewer({ jobId, apiBase }) {
  const [log, setLog] = useState(null)
  const [isOpen, setIsOpen] = useState(false)
  const [loading, setLoading] = useState(false)

  const handleViewLog = async () => {
    if (isOpen) {
      setIsOpen(false)
      return
    }

    if (log !== null) {
      setIsOpen(true)
      return
    }

    if (!jobId) return
    setLoading(true)

    try {
      const res = await fetch(`${apiBase}/api/log/${jobId}`)
      const data = await res.json()
      setLog(data.log || 'No log content.')
      setIsOpen(true)
    } catch (e) {
      setLog(`Error loading log: ${e.message}`)
      setIsOpen(true)
    } finally {
      setLoading(false)
    }
  }

  return (
    <>
      <button 
        onClick={handleViewLog} 
        style={{
          ...styles.button,
          ...styles.buttonLog,
          ...(loading && styles.buttonDisabled)
        }}
        disabled={loading}
      >
        {loading ? 'Loading...' : isOpen ? 'Hide Log' : 'View Pipeline Log'}
      </button>
      {isOpen && log && (
        <div style={styles.logViewer}>
          {log}
        </div>
      )}
    </>
  )
}