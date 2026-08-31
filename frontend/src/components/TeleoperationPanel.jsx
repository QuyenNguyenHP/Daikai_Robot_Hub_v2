import { useCallback, useEffect, useRef, useState } from 'react'
import {
  getTeleoperationStatus,
  startTeleoperation,
  stopTeleoperation,
} from '../services/api'


export function TeleoperationPanel() {
  const [status, setStatus] = useState({ running: false, output: [] })
  const [inputMode, setInputMode] = useState('controller')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notification, setNotification] = useState(null)
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

  const start = async () => {
    const confirmed = window.confirm(
      'Start R1-A5 teleoperation with --motion? Keep the emergency stop ready. ' +
      'The tested R1 firmware may not accept locomotion commands in FSM mode 816.'
    )
    if (!confirmed) return
    setBusy(true)
    setError('')
    try {
      const result = await startTeleoperation(inputMode)
      setStatus(result)
      setNotification({
        type: 'started',
        message: 'Teleoperation started. Open the address below in the Quest 3 browser.',
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
        message: 'Teleoperation stopped. The Quest 3 session has been closed.',
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

  return (
    <section className="panel teleoperation-panel">
      <div className="teleoperation-heading">
        <div>
          <p className="eyebrow">XR TELEOPERATION</p>
          <h2>Hand and arm control</h2>
        </div>
        <span className={`status-pill ${status.running ? 'live' : ''}`}>
          <i /> {status.running ? `Running · PID ${status.pid}` : 'Stopped'}
        </span>
      </div>

      <p className="teleoperation-warning">
        Motion is enabled. On the tested R1-A5 firmware, arm SDK mode 816 may block
        locomotion commands. Keep the robot in view and the emergency stop ready.
      </p>

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
          <button className="button danger" disabled={busy} onClick={stop}>Stop teleoperation</button>
        ) : (
          <button className="button primary" disabled={busy} onClick={start}>Start teleoperation</button>
        )}
      </div>

      {status.output?.length > 0 && (
        <pre className="teleoperation-output">{status.output.join('\n')}</pre>
      )}
      {error && <p className="error-message">{error}</p>}
    </section>
  )
}
