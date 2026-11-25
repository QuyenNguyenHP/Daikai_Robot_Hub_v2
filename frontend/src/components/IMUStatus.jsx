import { useEffect, useState } from 'react'
import { getRobotIMUWebSocketUrl } from '../services/api'

const number = (value) => Number.isFinite(value) ? value.toFixed(2) : '—'

export function IMUStatus() {
  const [status, setStatus] = useState(null)
  const [error, setError] = useState('')
  useEffect(() => {
    let active = true
    let socket = null
    let reconnectTimer = null
    let reconnectDelay = 1000

    const connect = () => {
      socket = new WebSocket(getRobotIMUWebSocketUrl())
      socket.onopen = () => {
        reconnectDelay = 1000
        if (active) setError('')
      }
      socket.onmessage = (event) => {
        if (!active) return
        try {
          setStatus(JSON.parse(event.data))
          setError('')
        } catch {
          setError('The IMU status update could not be decoded.')
        }
      }
      socket.onclose = () => {
        if (!active) return
        setStatus(null)
        setError('IMU status connection lost. Reconnecting…')
        reconnectTimer = window.setTimeout(connect, reconnectDelay)
        reconnectDelay = Math.min(reconnectDelay * 2, 5000)
      }
    }

    connect()
    return () => {
      active = false
      if (reconnectTimer !== null) window.clearTimeout(reconnectTimer)
      if (socket && socket.readyState < WebSocket.CLOSING) socket.close()
    }
  }, [])

  const connected = Boolean(status?.connected && !error)
  const imu = connected ? status.imu : null
  const groups = [
    ['ORIENTATION', 'rpy_deg', ['Roll', 'Pitch', 'Yaw'], '°'],
    ['ANGULAR VELOCITY', 'gyroscope_rad_s', ['X', 'Y', 'Z'], 'rad/s'],
    ['ACCELERATION', 'accelerometer_m_s2', ['X', 'Y', 'Z'], 'm/s²'],
    ['QUATERNION', 'quaternion_wxyz', ['W', 'X', 'Y', 'Z'], ''],
  ]
  return (
    <section className="panel imu-panel" aria-label="IMU telemetry">
      <div className="panel-heading">
        <div><p className="eyebrow">ROBOT TELEMETRY</p><h2>IMU</h2></div>
        <span className={`status-pill ${connected ? 'live' : ''}`}><i />{connected ? 'Live' : status?.state === 'stale' ? 'Stale' : 'Offline'}</span>
      </div>
      <div className="imu-metrics">
        {groups.map(([title, key, axes, unit]) => (
          <div key={key} className="imu-group">
            <h3>{title} <small>{unit}</small></h3>
            <dl>{axes.map((axis, index) => <div key={axis}><dt>{axis}</dt><dd>{number(imu?.[key]?.[index])}</dd></div>)}</dl>
          </div>
        ))}
      </div>
      <p className="imu-detail">Temperature: {imu ? `${imu.temperature_c} °C` : '—'}</p>
      {(error || status?.error || !connected) && <p className="imu-detail">{error || status?.error || (status?.state === 'stale' ? 'IMU telemetry is stale.' : 'Waiting for IMU telemetry…')}</p>}
    </section>
  )
}
