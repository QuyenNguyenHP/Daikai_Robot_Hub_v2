import { useEffect, useState } from 'react'
import {
  getRobotAutoWalkWebSocketUrl,
  getRobotStereoStreamUrl,
  getRobotStereoWebSocketUrl,
  startRobotAutoWalk,
  startRobotStereoView,
  stopRobotAutoWalk,
  stopRobotStereoView,
} from '../services/api'

function Monitor({ title, view, running, streamVersion }) {
  return (
    <section className="panel stereo-monitor-panel">
      <div className="stereo-monitor-heading">
        <h2>{title}</h2>
        <span className={`status-pill ${running ? 'live' : ''}`}><i /> {running ? 'Live' : 'Offline'}</span>
      </div>
      <div className="stereo-monitor">
        {running ? <img src={getRobotStereoStreamUrl(view, streamVersion)} alt={`${title} live monitor`} /> : (
          <div className="camera-placeholder"><div className="camera-icon">⌾</div><strong>{title} is offline</strong><span>Start distance monitor to activate this view</span></div>
        )}
      </div>
    </section>
  )
}

export function ObjectDistancePage() {
  const [stereo, setStereo] = useState(null)
  const [walk, setWalk] = useState(null)
  const [busyAction, setBusyAction] = useState('')
  const [error, setError] = useState('')
  const [streamVersion, setStreamVersion] = useState(0)
  const [settings, setSettings] = useState({
    forward_steps: 2,
    max_right_turns: 10,
    clearance_m: 0.5,
    forward_speed_m_s: 0.4,
    turn_speed_rad_s: 1,
  })

  useEffect(() => {
    let active = true
    let socket
    let reconnectTimer
    const connect = () => {
      socket = new WebSocket(getRobotStereoWebSocketUrl())
      socket.onmessage = (event) => {
        if (active) setStereo(JSON.parse(event.data))
      }
      socket.onclose = () => {
        if (active) reconnectTimer = window.setTimeout(connect, 1000)
      }
    }
    connect()
    let walkSocket
    let walkReconnectTimer
    const connectWalk = () => {
      walkSocket = new WebSocket(getRobotAutoWalkWebSocketUrl())
      walkSocket.onmessage = (event) => {
        if (!active) return
        try {
          setWalk(JSON.parse(event.data))
        } catch {
          setError('Autonomous walk status could not be decoded.')
        }
      }
      walkSocket.onclose = () => {
        if (active) walkReconnectTimer = window.setTimeout(connectWalk, 1000)
      }
    }
    connectWalk()
    return () => {
      active = false
      window.clearTimeout(reconnectTimer)
      window.clearTimeout(walkReconnectTimer)
      if (socket?.readyState < WebSocket.CLOSING) socket.close()
      if (walkSocket?.readyState < WebSocket.CLOSING) walkSocket.close()
    }
  }, [])

  const updateSetting = (name) => (event) => setSettings((current) => ({ ...current, [name]: Number(event.target.value) }))

  const startWalk = async () => {
    setBusyAction('start-walk')
    setError('')
    try {
      setWalk(await startRobotAutoWalk(settings))
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setBusyAction('')
    }
  }

  const stopWalk = async () => {
    setBusyAction('stop-walk')
    setError('')
    try {
      setWalk(await stopRobotAutoWalk())
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setBusyAction('')
    }
  }

  const startDistance = async () => {
    setBusyAction('start-distance')
    setError('')
    try {
      setStereo(await startRobotStereoView('depth'))
      setStreamVersion((version) => version + 1)
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setBusyAction('')
    }
  }

  const stopDistance = async () => {
    setBusyAction('stop-distance')
    setError('')
    try {
      setStereo(await stopRobotStereoView('depth'))
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setBusyAction('')
    }
  }

  const running = Boolean(walk?.running)
  const event = walk?.event
  const fields = [
    ['forward_steps', 'Forward steps', 1, 100, 1, 'steps'],
    ['max_right_turns', 'Maximum right turns', 1, 20, 1, 'turns'],
    ['clearance_m', 'Obstacle clearance', 0.3, 5, 0.1, 'm'],
    ['forward_speed_m_s', 'Forward speed', 0.01, 0.5, 0.01, 'm/s'],
    ['turn_speed_rad_s', 'Turn speed', 0.01, 1, 0.01, 'rad/s'],
  ]

  return (
    <div className="object-distance-page">
      <section className="stereo-page-heading">
        <div><h1>Autonomous Walk</h1><p>Stereo distance uses the left and right cameras to check the center travel corridor.</p></div>
        <div className="stereo-page-actions">
          <span className={`status-pill ${stereo?.views?.depth ? 'live' : ''}`}><i /> {stereo?.views?.depth ? 'Distance live' : 'Distance off'}</span>
          {stereo?.views?.depth
            ? <button type="button" className="button secondary" disabled={Boolean(busyAction)} onClick={stopDistance}>{busyAction === 'stop-distance' ? 'Stopping…' : 'Stop distance monitor'}</button>
            : <button type="button" className="button primary" disabled={Boolean(busyAction)} onClick={startDistance}>{busyAction === 'start-distance' ? 'Starting…' : 'Start distance monitor'}</button>}
        </div>
      </section>

      {(error || walk?.error || stereo?.error) && <p className="error-message stereo-page-error">{error || walk?.error || stereo?.error}</p>}

      <section className="panel auto-walk-panel">
        <div className="auto-walk-heading">
          <div><p className="eyebrow">ROUTE SETTINGS</p><h2>Walk and avoid obstacles</h2></div>
          <div className="auto-walk-actions">
            {running
              ? <button type="button" className="button danger" disabled={Boolean(busyAction)} onClick={stopWalk}>{busyAction === 'stop-walk' ? 'Stopping…' : 'Stop walking'}</button>
              : <button type="button" className="button primary" disabled={Boolean(busyAction) || walk?.configured === false} onClick={startWalk}>{busyAction === 'start-walk' ? 'Starting…' : 'Start autonomous walk'}</button>}
          </div>
        </div>
        <div className="auto-walk-settings">
          {fields.map(([name, label, min, max, step, unit]) => <label key={name}><span>{label}</span><div><input type="number" value={settings[name]} min={min} max={max} step={step} disabled={running || Boolean(busyAction)} onChange={updateSetting(name)} /><small>{unit}</small></div></label>)}
        </div>
        <div className="auto-walk-status"><div className={`auto-walk-event ${event?.type || ''}`}><strong>{event?.message || 'Ready to start.'}</strong>{event?.distance_m != null && <span>Measured clearance: {event.distance_m.toFixed(2)} m</span>}{event?.completed_steps != null && <span>{event.completed_steps}/{event.target_steps} steps · {event.completed_turns} right turn(s)</span>}</div></div>
        {walk?.events?.some((item) => ['step', 'turn'].includes(item.type)) && <div className="auto-walk-history">{walk.events.filter((item) => ['step', 'turn'].includes(item.type)).map((item, index) => <div className={item.type} key={`${item.type}-${index}`}><strong>{item.type === 'step' ? 'Forward' : 'Turn right'}</strong><span>{item.message} Clearance {item.distance_m.toFixed(2)} m.</span></div>)}</div>}
      </section>

      <div className="distance-camera-grid">
        <Monitor title="Left camera" view="left" running={Boolean(stereo?.views?.left)} streamVersion={streamVersion} />
        <Monitor title="Metric depth heatmap" view="depth" running={Boolean(stereo?.views?.depth)} streamVersion={streamVersion} />
      </div>
      <section className="panel stereo-metrics-panel center-corridor-panel"><p className="eyebrow">CENTER TRAVEL CORRIDOR</p><h2>{stereo?.obstacle_distance_m == null ? 'No reliable depth' : `${stereo.obstacle_distance_m.toFixed(2)} m clearance`}</h2><p>The highlighted center rectangle is the only image region used to decide whether the robot moves forward or turns right.</p><div className="stereo-metrics"><div><strong>{stereo?.fps ?? '—'}</strong><span>FPS</span></div><div><strong>{stereo?.stereo_ms ?? '—'}</strong><span>Stereo ms</span></div><div><strong>2</strong><span>Cameras used for depth</span></div><div><strong>{stereo?.pair_delta_ms ?? '—'}</strong><span>Pair delta ms</span></div></div></section>
      <p className="stereo-safety-note">Stereo depth is a perception estimate, not a safety-rated collision sensor. Keep the emergency stop ready.</p>
    </div>
  )
}
