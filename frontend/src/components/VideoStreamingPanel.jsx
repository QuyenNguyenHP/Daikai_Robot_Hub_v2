import { useCallback, useEffect, useRef, useState } from 'react'
import {
  getRobotServices,
  getVideoStreamFeedUrl,
  getVideoStreamStatus,
  startVideoStream,
  stopVideoStream,
} from '../services/api'


export function VideoStreamingPanel() {
  const [status, setStatus] = useState({ running: false, output: [] })
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState(null)
  const [stereoService, setStereoService] = useState(null)
  const [serviceError, setServiceError] = useState('')
  const [feedKey, setFeedKey] = useState(0)
  const mounted = useRef(true)

  const refresh = useCallback(async () => {
    try {
      const result = await getVideoStreamStatus()
      if (mounted.current) setStatus(result)
    } catch (error) {
      if (mounted.current) setMessage({ type: 'error', text: error.message })
    }
  }, [])

  useEffect(() => {
    mounted.current = true
    void refresh()
    const timer = window.setInterval(refresh, 2000)
    return () => {
      mounted.current = false
      window.clearInterval(timer)
    }
  }, [refresh])

  useEffect(() => {
    let active = true
    const refreshService = async () => {
      try {
        const result = await getRobotServices()
        if (!active) return
        setStereoService(
          (result.services || []).find((service) => service.name === 'stereo_patch_pc1') || null
        )
        setServiceError('')
      } catch (error) {
        if (active) setServiceError(error.message)
      }
    }
    void refreshService()
    const timer = window.setInterval(refreshService, 5000)
    return () => {
      active = false
      window.clearInterval(timer)
    }
  }, [])

  const start = async () => {
    setBusy(true)
    setMessage(null)
    try {
      setStatus(await startVideoStream())
      setFeedKey((key) => key + 1)
      setMessage({ type: 'success', text: 'Live robot video started.' })
    } catch (error) {
      setMessage({ type: 'error', text: error.message })
    } finally {
      setBusy(false)
    }
  }

  const stop = async () => {
    setBusy(true)
    setMessage(null)
    try {
      setStatus(await stopVideoStream())
      setMessage({ type: 'success', text: 'Live robot video stopped.' })
    } catch (error) {
      setMessage({ type: 'error', text: error.message })
    } finally {
      setBusy(false)
    }
  }

  const serviceReady = Boolean(stereoService?.enabled) && !serviceError

  return (
    <section className="panel video-stream-panel">
      <div className="panel-heading video-stream-heading">
        <div>
          <p className="eyebrow">LIVE VIDEO</p>
          <h2>Robot camera</h2>
        </div>
        <span className={`status-pill ${status.running ? 'live' : ''}`}>
          <i /> {status.running ? 'Live' : 'Stopped'}
        </span>
      </div>

      <p className="video-stream-description">
        View the robot&apos;s RTP/H.264 camera feed directly in this dashboard.
      </p>

      <div className={`video-stream-prerequisite ${serviceReady ? 'ready' : ''}`}>
        <span><i /> stereo_patch_pc1</span>
        <strong>{serviceReady ? 'Service on' : 'Service must be turned on'}</strong>
      </div>
      {serviceError && <p className="mode-detail video-stream-service-error">{serviceError}</p>}

      <div className={`video-viewer ${status.running ? 'active' : ''}`}>
        {status.running ? (
          <img
            key={feedKey}
            src={`${getVideoStreamFeedUrl()}?session=${feedKey}`}
            alt="Live view from the robot camera"
            onError={() => setMessage({ type: 'error', text: 'The live video feed could not be displayed.' })}
          />
        ) : (
          <div className="video-viewer-placeholder">
            <span aria-hidden="true">▶</span>
            <strong>Camera preview is off</strong>
            <small>Start live view to show the robot video here.</small>
          </div>
        )}
      </div>

      <div className="video-stream-actions">
        {status.running ? (
          <button type="button" className="button danger" disabled={busy} onClick={stop}>
            {busy ? 'Stopping…' : 'Stop live view'}
          </button>
        ) : (
          <button
            type="button"
            className="button primary"
            disabled={busy || !serviceReady}
            title={serviceReady ? 'Start live view' : 'Turn on stereo_patch_pc1 in System Services first'}
            onClick={start}
          >
            {busy ? 'Starting…' : 'Start live view'}
          </button>
        )}
      </div>

      {message && <p className={`${message.type}-message`}>{message.text}</p>}
      {status.output?.length > 0 && (
        <details className="video-stream-output">
          <summary>GStreamer output</summary>
          <pre>{status.output.join('\n')}</pre>
        </details>
      )}
    </section>
  )
}
