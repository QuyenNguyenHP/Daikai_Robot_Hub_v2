import { CameraSourceSelect } from './CameraSourceSelect'
import { HudIcon } from './HudIcon'
import { FaceEnrollmentDialog } from './FaceEnrollmentDialog'
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
  const [enrolling, setEnrolling] = useState(false)

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
          setMessage({ type: 'error', text: 'Vision status could not be decoded.' })
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
      setMessage({ type: 'success', text: 'Vision video started.' })
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
      setMessage({ type: 'success', text: 'Vision video stopped.' })
    } catch (error) {
      setMessage({ type: 'error', text: error.message })
    } finally {
      setBusy(false)
    }
  }

  const running = Boolean(status?.running && status?.views?.detection && status?.state !== 'error')
  const loading = running && status?.state === 'loading'

  return (
    <section className="panel video-stream-panel">
      <div className="panel-heading video-stream-heading">
        <div>
          <p className="eyebrow">LIVE VIDEO</p>
          <h2>Vision</h2>
        </div>
        <span className={`status-pill ${running ? 'live' : ''}`}>
          <i /> {loading ? 'Preparing AI…' : running ? (status?.connected ? 'Live' : 'Waiting for camera…') : 'Stopped'}
        </span>
      </div>

      <CameraSourceSelect status={status} disabled={busy} onStatus={setStatus}
        onError={(text) => setMessage({ type: 'error', text })} />
      <p className="video-stream-description">
        {status?.camera_source === 'd415'
          ? 'Person detection and face recognition using the USB RealSense D415.'
          : `Person detection and face recognition using the stereo cameras on UDP ports ${status?.ports?.left || 5002} and ${status?.ports?.right || 5003}.`}
      </p>

      <div
        className={`video-viewer ${running ? 'active' : ''}`}
        style={{ aspectRatio: status?.frame_size ? status.frame_size.join(' / ') : status?.camera_source === 'd415' ? '16 / 9' : '544 / 448' }}
      >
        {running ? (
          <img
            key={feedKey}
            src={`${getRobotStereoStreamUrl('detection', feedKey)}`}
            alt="Live Vision from the robot camera"
            onError={() => setMessage({ type: 'error', text: 'The Vision feed could not be displayed.' })}
          />
        ) : (
          <div className="video-viewer-placeholder">
            <span aria-hidden="true"><HudIcon name="vision" /></span>
            <strong>Vision is off</strong>
            <small>Start live view to detect people and recognize faces from the robot camera.</small>
          </div>
        )}
      </div>

      <div className="video-stream-actions">
        <button type="button" className="button secondary" onClick={() => setEnrolling(true)}><HudIcon name="face" /> Register face</button>
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

      {status?.error && <p className="error-message">{status.error}</p>}
      {status?.face_recognition_error && <p className="error-message">Face recognition unavailable: {status.face_recognition_error}</p>}
      {running && <p className="video-stream-description">{status?.frame_size?.join('×') || ''} {status?.camera_source === 'd415' ? status?.preview_mode : ''} · FPS: {status?.fps ?? 0} · AI: {status?.yolo_ms ?? 0} ms · People: {status?.detections?.length || 0} · Faces: {status?.faces?.length || 0}</p>}
      {running && status?.faces?.length > 0 && <p className="video-stream-description">Faces: {status.faces.map((face) => face.name).join(', ')}</p>}
      {message && <p className={`${message.type}-message`}>{message.text}</p>}
      {running && status?.detections?.length > 0 && (
        <p className="video-stream-description">
          Detecting: {status.detections.map((item) => item.name).join(', ')}
        </p>
      )}
      {enrolling && <FaceEnrollmentDialog onClose={() => setEnrolling(false)} />}
    </section>
  )
}
