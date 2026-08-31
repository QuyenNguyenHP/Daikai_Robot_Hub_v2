import { useCallback, useEffect, useRef, useState } from 'react'
import {
  getRobotServices,
  getVideoStreamStatus,
  startVideoStream,
  stopVideoStream,
} from '../services/api'


export function VideoStreamingPanel() {
  const [destinationIp, setDestinationIp] = useState('')
  const [status, setStatus] = useState({ running: false, output: [] })
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState(null)
  const [stereoService, setStereoService] = useState(null)
  const [serviceError, setServiceError] = useState('')
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

  const submit = async (event) => {
    event.preventDefault()
    setBusy(true)
    setMessage(null)
    try {
      const result = await startVideoStream(destinationIp.trim())
      setStatus(result)
      setMessage({
        type: 'success',
        text: `Relaying RTP/H.264 video to ${result.destination_ip}:5000.`,
      })
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
      setMessage({ type: 'success', text: 'Video relay stopped.' })
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
          <p className="eyebrow">VIDEO RELAY</p>
          <h2>Stream to another device</h2>
        </div>
        <span className={`status-pill ${status.running ? 'live' : ''}`}>
          <i /> {status.running ? 'Streaming' : 'Stopped'}
        </span>
      </div>

      <p className="video-stream-description">
        Receives RTP/H.264 on UDP port 5001 and forwards it to UDP port 5000
        on the destination PC or laptop.
      </p>

      <div className={`video-stream-prerequisite ${serviceReady ? 'ready' : ''}`}>
        <span><i /> stereo_patch_pc1</span>
        <strong>{serviceReady ? 'Service on' : 'Service must be turned on'}</strong>
      </div>
      {serviceError && <p className="mode-detail video-stream-service-error">{serviceError}</p>}

      <form className="video-stream-form" onSubmit={submit}>
        <label>
          <span>Destination device IP</span>
          <input
            className="text-input"
            type="text"
            inputMode="decimal"
            placeholder="192.168.0.52"
            value={status.running ? status.destination_ip || '' : destinationIp}
            disabled={status.running || busy}
            required
            onChange={(event) => setDestinationIp(event.target.value)}
          />
        </label>
        {status.running ? (
          <button type="button" className="button danger" disabled={busy} onClick={stop}>
            {busy ? 'Stopping…' : 'Stop streaming'}
          </button>
        ) : (
          <button
            type="submit"
            className="button primary"
            disabled={busy || !destinationIp.trim() || !serviceReady}
            title={serviceReady ? 'Start streaming' : 'Turn on stereo_patch_pc1 in System Services first'}
          >
            {busy ? 'Starting…' : 'Start streaming'}
          </button>
        )}
      </form>

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
