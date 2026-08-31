import { useCallback, useEffect, useRef, useState } from 'react'
import {
  getRobotModeWebSocketUrl,
  getTeleoperationStatus,
  startTeleoperation,
  startTeleoperationTracking,
  stopTeleoperation,
} from '../services/api'


export function TeleoperationPanel() {
  const [status, setStatus] = useState({ running: false, output: [] })
  const [inputMode, setInputMode] = useState('controller')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notification, setNotification] = useState(null)
  const [mode, setMode] = useState(null)
  const [modeError, setModeError] = useState('')
  const mounted = useRef(true)
  const questHost = window.location.hostname
  const questUrl = `https://${questHost}:8012/?ws=wss://${questHost}:8012`

  const refresh = useCallback(async () => {
    try {
      const result = await getTeleoperationStatus()
      if (mounted.current) {
        setStatus(result)
        setError('')
      }
    } catch (requestError) {
      if (mounted.current) setError(requestError.message)
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
    let socket = null
    let reconnectTimer = null
    let reconnectDelay = 1000

    const connect = () => {
      socket = new WebSocket(getRobotModeWebSocketUrl())
      socket.onopen = () => {
        reconnectDelay = 1000
        if (active) setModeError('')
      }
      socket.onmessage = (event) => {
        if (!active) return
        try {
          const result = JSON.parse(event.data)
          if (result.error) {
            setModeError(result.error)
          } else {
            setMode(result)
            setModeError('')
          }
        } catch {
          setModeError('The robot mode update could not be decoded.')
        }
      }
      socket.onclose = () => {
        if (!active) return
        setModeError('Robot mode connection lost. Reconnecting…')
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

  const start = async () => {
    setBusy(true)
    setError('')
    try {
      const result = await startTeleoperation(inputMode)
      setStatus(result)
      setNotification({
        type: 'started',
        message: 'XR server launched. Connect Quest 3, then press Start robot tracking.',
      })
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setBusy(false)
    }
  }

  const beginTracking = async () => {
    const confirmed = window.confirm(
      'Start robot tracking now? Keep the emergency stop ready and align your arms ' +
      'with the robot before continuing.'
    )
    if (!confirmed) return
    setBusy(true)
    setError('')
    try {
      setStatus(await startTeleoperationTracking())
      setNotification({
        type: 'started',
        message: 'Robot tracking started. The frontend button replaced keyboard R.',
      })
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setBusy(false)
    }
  }

  const stop = async () => {
    const confirmed = window.confirm(
      'Stop teleoperation and disconnect the Quest 3 session?'
    )
    if (!confirmed) return
    setBusy(true)
    setError('')
    try {
      setStatus(await stopTeleoperation())
      setNotification({
        type: 'stopped',
        message: 'Teleoperation stopped and the robot was returned to FSM mode 811.',
      })
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setBusy(false)
    }
  }

  const copyQuestUrl = async () => {
    try {
      await navigator.clipboard.writeText(questUrl)
      setNotification({
        type: 'started',
        message: 'Quest 3 address copied to the clipboard.',
      })
    } catch {
      setError('Could not copy the Quest 3 address. Copy it manually below.')
    }
  }

  const launchReady = mode?.fsm_id === 811 && !mode?.stale && !modeError

  return (
    <section className="panel teleoperation-panel">
      <div className="teleoperation-heading">
        <div>
          <p className="eyebrow">XR TELEOPERATION</p>
          <h2>Hand and arm control</h2>
        </div>
        <span className={`status-pill ${status.running ? 'live' : ''}`}>
          <i /> {status.stopping
            ? 'Stopping · FSM 811 requested'
            : status.tracking
              ? `Tracking · PID ${status.pid}`
              : status.running
                ? `Ready · PID ${status.pid}`
                : 'Stopped'}
        </span>
      </div>

      <p className="teleoperation-warning">
        Motion is enabled. On the tested R1-A5 firmware, arm SDK mode 816 may block
        locomotion commands. Keep the robot in view and the emergency stop ready.
      </p>

      <div className={`teleoperation-mode ${launchReady ? 'ready' : ''}`}>
        <div>
          <span>ROBOT MODE</span>
          <strong>{mode?.display || 'Waiting for robot mode…'}</strong>
        </div>
        <small>
          {launchReady
            ? 'Ready to launch teleoperation'
            : 'Launch requires locomotion mode 811'}
        </small>
      </div>
      {modeError && <p className="mode-detail teleoperation-mode-error">{modeError}</p>}

      {notification && (
        <div className={`teleoperation-notification ${notification.type}`} role="status">
          <div>
            <strong>{notification.type === 'started' ? 'Quest 3 ready' : 'Session ended'}</strong>
            <span>{notification.message}</span>
          </div>
          <button type="button" aria-label="Dismiss notification" onClick={() => setNotification(null)}>×</button>
        </div>
      )}

      {status.running && (
        <div className="quest-access-card">
          <div>
            <span>QUEST 3 ACCESS</span>
            <strong>Open this address in the Quest browser, then select Virtual Reality.</strong>
          </div>
          <code>{questUrl}</code>
          <button type="button" className="button secondary" onClick={copyQuestUrl}>Copy address</button>
        </div>
      )}

      <div className="teleoperation-controls">
        <label>
          <span>Input mode</span>
          <select
            value={status.running ? status.input_mode : inputMode}
            disabled={status.running || busy}
            onChange={(event) => setInputMode(event.target.value)}
          >
            <option value="controller">Controller</option>
            <option value="hand">Hand tracking</option>
          </select>
        </label>
        <div className="teleoperation-config">
          <span>R1_A5 · 30 Hz · eth10</span>
          <span>Pass-through · Images off · Motion on</span>
        </div>
        {status.running ? (
          <div className="teleoperation-actions">
            {!status.tracking && !status.stopping && (
              <button className="button primary" disabled={busy} onClick={beginTracking}>Start robot tracking</button>
            )}
            <button className="button danger" disabled={busy || status.stopping} onClick={stop}>Stop teleoperation</button>
          </div>
        ) : (
          <button
            className="button primary"
            disabled={busy || !launchReady}
            onClick={start}
            title={launchReady ? 'Launch teleoperation' : 'Robot must be in locomotion mode 811'}
          >
            Launch teleoperation
          </button>
        )}
      </div>

      {status.output?.length > 0 && (
        <pre className="teleoperation-output">{status.output.join('\n')}</pre>
      )}
      {error && <p className="error-message">{error}</p>}
    </section>
  )
}
