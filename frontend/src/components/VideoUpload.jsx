import { useState } from 'react'
import { styles } from '../styles'

export default function VideoUpload({ apiBase, onUploadStart }) {
  const [file, setFile] = useState(null)
  const [loading, setLoading] = useState(false)
  const [status, setStatus] = useState(null)

  const handleFileChange = (e) => {
    setFile(e.target.files[0])
  }

  const handleUpload = async () => {
    if (!file) {
      setStatus({ type: 'error', message: 'Please select a video file.' })
      return
    }

    setLoading(true)
    setStatus({ type: 'info', message: 'Uploading...' })

    const formData = new FormData()
    formData.append('video', file)

    try {
      const res = await fetch(`${apiBase}/api/upload`, {
        method: 'POST',
        body: formData,
      })
      const data = await res.json()

      if (res.ok) {
        setStatus({
          type: 'success',
          message: `Upload complete. Processing started (Job: ${data.job_id.slice(0, 8)}...)`,
        })
        onUploadStart(data.job_id)
        setFile(null)
      } else {
        setStatus({ type: 'error', message: `Error: ${data.error || 'Upload failed'}` })
      }
    } catch (e) {
      setStatus({ type: 'error', message: `Network error: ${e.message}` })
    } finally {
      setLoading(false)
    }
  }

  const getStatusStyle = () => {
    if (!status) return {}
    if (status.type === 'info') return { ...styles.status, ...styles.statusInfo }
    if (status.type === 'success') return { ...styles.status, ...styles.statusSuccess }
    if (status.type === 'error') return { ...styles.status, ...styles.statusError }
    return styles.status
  }

  return (
    <div style={styles.card}>
      <h2 style={styles.cardHeading}>Upload Video</h2>
      <label htmlFor="videoFile" style={styles.label}>Select a lecture video (MP4, MKV, MOV, AVI, WEBM)</label>
      <input
        type="file"
        id="videoFile"
        accept=".mp4,.mkv,.mov,.avi,.webm,.flv,.m4v,.mpeg"
        onChange={handleFileChange}
        style={styles.fileInput}
      />
      <br />
      <button 
        onClick={handleUpload} 
        disabled={loading}
        style={{
          ...styles.button,
          ...(loading && styles.buttonDisabled)
        }}
      >
        {loading ? 'Uploading...' : 'Upload & Process'}
      </button>
      {status && (
        <div style={getStatusStyle()}>
          {status.message}
        </div>
      )}
    </div>
  )
}