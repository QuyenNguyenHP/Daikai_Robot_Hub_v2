import { HudIcon } from './HudIcon'
import { useCallback, useEffect, useRef, useState } from 'react'
import { executeRobotArmAction, getRobotArmActions, getRobotControlStatusWebSocketUrl } from '../services/api'

function actionIcon(name) {
  const value = name.toLowerCase().replace(/[ _-]+/g, ' ')
  if (/release/.test(value)) return 'release'
  if (/clamp|clap/.test(value)) return 'clap'
  if (/shake|handshake/.test(value)) return 'handshake'
  if (/kiss/.test(value)) return 'kiss'
  if (/heart/.test(value)) return 'heart'
  if (/hug/.test(value)) return 'hug'
  if (/high five/.test(value)) return 'hand'
  if (/wave/.test(value)) return 'wave'
  if (/reject|refuse|cross/.test(value)) return 'refuse'
  if (/x ray|ultraman|ray/.test(value)) return 'ray'
  if (/box|punch/.test(value)) return 'punch'
  if (/hand.*up/.test(value)) return 'raised'
  if (/dance/.test(value)) return 'dance'
  if (/bow/.test(value)) return 'bow'
  return 'robot'
}

function actionLabel(name) {
  if (name === 'clamp') return 'Clap'
  return name.replace(/[_-]+/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase())
}

export function RobotActionsPanel() {
  const [actions, setActions] = useState([])
  const [status, setStatus] = useState(null)
  const [online, setOnline] = useState(false)
  const [loading, setLoading] = useState(false)
  const [sending, setSending] = useState(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [loaded, setLoaded] = useState(false)
  const inFlight = useRef(false)
  const mounted = useRef(false)

  const refresh = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const result = await getRobotArmActions()
      if (!mounted.current) return
      setActions(result.arm_actions || [])
      setLoaded(true)
    } catch (failure) {
      if (mounted.current) setError(failure.message)
    } finally {
      if (mounted.current) setLoading(false)
    }
  }, [])

  useEffect(() => {
    mounted.current = true
    let active = true
    let socket
    let timer
    const connect = () => {
      socket = new WebSocket(getRobotControlStatusWebSocketUrl())
      socket.onmessage = (event) => {
        if (!active) return
        try {
          const result = JSON.parse(event.data)
          setStatus(result)
          setOnline(true)
        } catch {
          setOnline(false)
        }
      }
      socket.onclose = () => {
        if (!active) return
        setOnline(false)
        timer = window.setTimeout(connect, 1000)
      }
    }
    connect()
    void refresh()
    return () => {
      active = false
      mounted.current = false
      window.clearTimeout(timer)
      if (socket?.readyState < WebSocket.CLOSING) socket.close()
    }
  }, [refresh])

  const cooldown = Math.ceil(status?.arm_action_cooldown_seconds || 0)
  const ready = online && status?.configured && status?.last_fsm_id === 811
  const disabled = !ready || loading || sending !== null || status?.busy || status?.polishing_active || cooldown > 0

  const execute = async (action) => {
    if (inFlight.current || disabled) return
    inFlight.current = true
    setSending(action.id)
    setError('')
    setNotice('')
    try {
      const result = await executeRobotArmAction(action.id)
      if (!mounted.current) return
      setStatus(result)
      setNotice(action.name === 'release_arm'
        ? 'Release arm accepted. Arm-action control is being returned.'
        : `${actionLabel(action.name)} accepted by the robot.`)
    } catch (failure) {
      if (mounted.current) setError(failure.message)
    } finally {
      inFlight.current = false
      if (mounted.current) setSending(null)
    }
  }

  return (
    <section className="panel robot-actions-panel" aria-labelledby="robot-actions-title">
      <div className="panel-heading">
        <div><p className="eyebrow">GESTURES & ACTIONS</p><h2 id="robot-actions-title"><HudIcon name="robot" /> Robot actions</h2></div>
        <span className={`status-pill ${ready && !disabled ? 'live' : ''}`}><i />{!online ? 'Offline' : sending !== null ? 'Sending…' : cooldown > 0 ? `Wait ${cooldown}s` : disabled ? 'Locked' : 'Ready'}</span>
      </div>
      <p className="control-safety">Keep space around both arms. Actions require locomotion mode (FSM 811).</p>
      <div className="arm-action-toolbar">
        <span>{loaded ? `${actions.length} actions available` : 'Load actions from the robot'}</span>
        <button type="button" className="button secondary" disabled={loading || sending !== null || status?.busy} onClick={refresh}><HudIcon name="refresh" />{loading ? 'Loading…' : 'Refresh'}</button>
      </div>
      <div className="arm-action-grid">
        {actions.map((action) => (
          <button type="button" className="arm-action-button" key={action.id} disabled={disabled} onClick={() => execute(action)} title={`${action.name} · ID ${action.id}`}>
            <span className="arm-action-icon"><HudIcon name={actionIcon(action.name)} /></span>
            <strong>{sending === action.id ? 'Sending…' : actionLabel(action.name)}</strong>
            <small>ID {action.id}</small>
          </button>
        ))}
      </div>
      {loaded && actions.length === 0 && <p className="mode-detail">The robot returned no available actions.</p>}
      {online && status?.last_fsm_id !== 811 && <p className="mode-detail">Enter locomotion FSM 811 using Robot controls to enable actions.</p>}
      {status?.polishing_active && <p className="mode-detail">Stop crankshaft polishing to use these actions.</p>}
      <p className="mode-detail">A 5-second interval starts after command acceptance to avoid overlapping actions. The robot does not report when a gesture finishes.</p>
      <div aria-live="polite">
        {notice && <p className="success-message">{notice}</p>}
        {error && <p className="error-message">{error}</p>}
      </div>
    </section>
  )
}
