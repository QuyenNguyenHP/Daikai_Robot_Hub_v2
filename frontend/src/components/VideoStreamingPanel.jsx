import { useEffect, useState } from 'react'
import {
  getRobotStereoStreamUrl,
  getRobotStereoWebSocketUrl,
  startRobotStereoView,
  stopRobotStereoView,
} from '../services/api'


export function VideoStreamingPanel() {
  const [status, setStatus] = useState(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState(null)
  const [feedKey, setFeedKey] = useState(0)

  useEffect(() => {
    let active = true
    let socket
    let reconnectTimer
    const connect = () => {
      socket = new WebSocket(getRobotStereoWebSocketUrl())
      socket.onmessage = (event) => {
        if (!active) return
        try {
          setStatus(JSON.parse(event.data))
        } catch {
          setMessage({ type: 'error', text: 'Object detection status could not be decoded.' })
        }
      }
      socket.onclose = () => {
        if (active) reconnectTimer = window.setTimeout(connect, 1000)
      }
    }
    connect()
    return () => {
      active = false
      window.clearTimeout(reconnectTimer)
      if (socket?.readyState < WebSocket.CLOSING) socket.close()
    }
  }, [])

  const start = async () => {
    setBusy(true)
    setMessage(null)
    try {
      setStatus(await startRobotStereoView('detection'))
      setFeedKey((key) => key + 1)
      setMessage({ type: 'success', text: 'Object detection video started.' })
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
      setStatus(await stopRobotStereoView('detection'))
      setMessage({ type: 'success', text: 'Object detection video stopped.' })
    } catch (error) {
      setMessage({ type: 'error', text: error.message })
    } finally {
      setBusy(false)
    }
  }

  const running = Boolean(status?.views?.detection)
  const loading = running && status?.state === 'loading'

  return (
    <section className="panel video-stream-panel">
      <div className="panel-heading video-stream-heading">
        <div>
          <p className="eyebrow">LIVE VIDEO</p>
          <h2>Object detection</h2>
        </div>
        <span className={`status-pill ${running ? 'live' : ''}`}>
          <i /> {loading ? 'Loading model…' : running ? 'Live' : 'Stopped'}
        </span>
      </div>

      <p className="video-stream-description">
        YOLO-World object detection using the stereo camera pair on UDP ports{' '}
        {status?.ports?.left || 5002} and {status?.ports?.right || 5003}.
      </p>

      <div
        className={`video-viewer ${running ? 'active' : ''}`}
        style={{ aspectRatio: '544 / 448' }}
      >
        {running ? (
          <img
            key={feedKey}
            src={`${getRobotStereoStreamUrl('detection', feedKey)}`}
            alt="Live object detection from the robot camera"
            onError={() => setMessage({ type: 'error', text: 'The object detection feed could not be displayed.' })}
          />
        ) : (
          <div className="video-viewer-placeholder">
            <span aria-hidden="true">⌾</span>
            <strong>Object detection is off</strong>
            <small>Start live view to detect objects from the robot camera.</small>
          </div>
        )}
      </div>

      <div className="video-stream-actions">
        {running ? (
          <button type="button" className="button danger" disabled={busy} onClick={stop}>
            {busy ? 'Stopping…' : 'Stop live view'}
          </button>
        ) : (
          <button type="button" className="button primary" disabled={busy || status?.view_configured?.detection === false} onClick={start}>
            {busy ? 'Starting…' : 'Start live view'}
          </button>
        )}
      </div>

      {message && <p className={`${message.type}-message`}>{message.text}</p>}
      {status?.detections?.length > 0 && (
        <p className="video-stream-description">
          Detecting: {status.detections.map((item) => item.name).join(', ')}
        </p>
      )}
    </section>
  )
}
