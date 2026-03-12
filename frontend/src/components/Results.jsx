import { useState, useEffect } from 'react'
import { styles } from '../styles'

export default function Results({ jobId, apiBase, show }) {
  const [results, setResults] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!show || !jobId) return

    const fetchResults = async () => {
      setLoading(true)
      setError(null)
      try {
        const res = await fetch(`${apiBase}/api/results/${jobId}`)
        const data = await res.json()
        setResults(data)
      } catch (e) {
        setError(`Error fetching results: ${e.message}`)
      } finally {
        setLoading(false)
      }
    }

    fetchResults()
  }, [jobId, apiBase, show])

  if (!show) return null

  if (loading) {
    return (
      <div style={styles.card}>
        <h2 style={styles.cardHeading}>Results</h2>
        <div style={{ ...styles.status, ...styles.statusInfo }}>
          Loading results...
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div style={styles.card}>
        <h2 style={styles.cardHeading}>Results</h2>
        <div style={{ ...styles.status, ...styles.statusError }}>
          {error}
        </div>
      </div>
    )
  }

  if (!results) return null

  return (
    <div style={styles.card}>
      <h2 style={styles.cardHeading}>Results</h2>
      <div style={styles.results}>
        {results.timestamps && results.timestamps.length > 0 && (
          <>
            <h3 style={styles.resultsHeading}>Chapters</h3>
            {results.timestamps.map((chapter, idx) => (
              <div key={idx} style={styles.chapter}>
                <span style={styles.chapterTime}>{chapter.time}</span>
                {' — '}
                <span style={styles.chapterTitle}>{chapter.title}</span>
              </div>
            ))}
          </>
        )}

        {results.summary && results.summary.length > 0 && (
          <>
            <h3 style={styles.resultsHeading}>Summaries</h3>
            {results.summary.map((item, idx) => (
              <div key={idx}>
                {Object.entries(item).map(([time, summaries]) =>
                  Object.entries(summaries).map(([title, text]) => (
                    <div key={`${idx}-${time}-${title}`} style={styles.chapter}>
                      <span style={styles.chapterTime}>{time}</span>
                      {' — '}
                      <span style={styles.chapterTitle}>{title}</span>
                      <p style={styles.chapterSummary}>{text}</p>
                    </div>
                  ))
                )}
              </div>
            ))}
          </>
        )}

        {results.transcript && (
          <>
            <h3 style={styles.resultsHeading}>Transcript</h3>
            <pre style={styles.resultsPreview}>{results.transcript}</pre>
          </>
        )}

        {!results.timestamps && !results.summary && !results.transcript && (
          <p>No results available yet.</p>
        )}
      </div>
    </div>
  )
}