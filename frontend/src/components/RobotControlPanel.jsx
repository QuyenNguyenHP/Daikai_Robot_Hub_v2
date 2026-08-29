import { useEffect, useRef, useState } from 'react'
import {
  controlRobot,
  getRobotControlStatus,
  getRobotModeWebSocketUrl,
} from '../services/api'
import SliderSizes from './SliderSizes'


const MOVEMENT_BUTTONS = [
  ['turn_left', '↶', 'Turn left'],
  ['forward', '↑', 'Forward'],
  ['turn_right', '↷', 'Turn right'],
  ['left', '←', 'Move left'],
  ['stop', '■', 'Stop'],
  ['right', '→', 'Move right'],
  [null, '', ''],
  ['backward', '↓', 'Backward'],
  [null, '', ''],
]
const MOVEMENT_ACTIONS = new Set(
  MOVEMENT_BUTTONS.filter(([action]) => action).map(([action]) => action),
)

export function RobotControlPanel() {
  const [status, setStatus] = useState(null)
  const [mode, setMode] = useState(null)
  const [modeError, setModeError] = useState('')
  const [busyAction, setBusyAction] = useState('')
  const [confirmEnable, setConfirmEnable] = useState(false)
  const [confirmStance, setConfirmStance] = useState(false)
  const [controlError, setControlError] = useState('')
  const [controlLocked, setControlLocked] = useState(false)
  const [polishingArm, setPolishingArm] = useState('right')
  const [polishingSpeed, setPolishingSpeed] = useState(120)
  const [polishingHold, setPolishingHold] = useState(0.05)
  const [showPolishingDialog, setShowPolishingDialog] = useState(false)
  const requestInFlight = useRef(false)

  useEffect(() => {
    let active = true
    getRobotControlStatus()
      .then((result) => {
        if (active) setStatus(result)
      })
      .catch(() => {})
    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    const timer = window.setInterval(() => {
      getRobotControlStatus().then(setStatus).catch(() => {})
    }, 1000)
    return () => window.clearInterval(timer)
  }, [])

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

  const send = async (action, options = {}) => {
    if (requestInFlight.current) return
    requestInFlight.current = true
    setBusyAction(action)
    setControlError('')
    try {
      const result = await controlRobot(action, options)
      setStatus(result)
      if (action === 'enable') setControlLocked(false)
    } catch (error) {
      if (!MOVEMENT_ACTIONS.has(action)) setControlError(error.message)
      try {
        setStatus(await getRobotControlStatus())
      } catch {
        // Keep the last known control state when status refresh also fails.
      }
    } finally {
      requestInFlight.current = false
      setBusyAction('')
    }
  }

  const configured = Boolean(status?.configured)
  const isZeroTorqueMode = mode?.fsm_id === 0
  const isStanceMode = mode?.fsm_id === 4
  const isLocomotionMode = [811, 816].includes(mode?.fsm_id)
  const locomotionActive = isLocomotionMode && !controlLocked
  const canToggleStanceMode = isZeroTorqueMode || isStanceMode || isLocomotionMode
  const stanceModeAction = isStanceMode ? 'zero_torque' : 'stance'
  const commandDisabled = !configured || !locomotionActive || Boolean(busyAction)
  const polishingActive = Boolean(status?.polishing_active)
  const polishingReady = mode?.fsm_id === 811
  const actionUnavailable = !configured || Boolean(busyAction) || polishingActive
  const canLieToStand = [0, 1].includes(mode?.fsm_id)
  const canStandToLie = [811, 816].includes(mode?.fsm_id)

  const togglePolishing = () => {
    if (polishingActive) {
      void send('crankshaft_stop')
      return
    }
    void send('crankshaft_start', {
      arm: polishingArm,
      speed_deg_s: Number(polishingSpeed),
      hold_seconds: Number(polishingHold),
    })
  }

  const confirmLocomotion = () => {
    setConfirmEnable(false)
    void send('enable')
  }

  const sendModeAction = (action) => {
    void send(action)
  }

  const confirmStanceMode = () => {
    setConfirmStance(false)
    setControlLocked(true)
    void send('stance')
  }

  const toggleStanceMode = () => {
    if (isLocomotionMode) {
      setConfirmStance(true)
      return
    }
    sendModeAction(stanceModeAction)
  }

  return (
    <section className="panel robot-control-panel">
      <div className="control-title-row">
        <div>
          <p className="eyebrow">ROBOT CONTROL</p>
          <h2>Robot controls</h2>
        </div>
        <span className={`status-pill ${locomotionActive ? 'live' : ''}`}>
          <i /> {locomotionActive ? 'Enabled' : 'Locked'}
        </span>
      </div>

      <p className="control-safety">
        Use only in a clear, flat area. Each movement command lasts one second.
      </p>

      <div className="robot-mode">
        <span>FSM MODE</span>
        <strong>{mode?.display || (modeError ? 'Unavailable' : 'Checking…')}</strong>
      </div>

      <div className="control-mode-actions">
        <button
          type="button"
          className="button secondary"
          disabled={!configured || Boolean(busyAction) || !canToggleStanceMode}
          onClick={toggleStanceMode}
        >
          {busyAction === 'stance'
            ? 'Entering stance…'
            : busyAction === 'zero_torque'
              ? 'Entering zero torque…'
              : isStanceMode
                ? 'Enter zero torque mode'
                : 'Enter stance mode'}
        </button>
        <button
          type="button"
          className="button primary"
          disabled={
            !configured
            || Boolean(busyAction)
            || locomotionActive
            || !isStanceMode
          }
          onClick={() => setConfirmEnable(true)}
        >
          {busyAction === 'enable' ? 'Enabling…' : 'Enable locomotion'}
        </button>
      </div>

      <div className="robot-control-group">
        <h3>Moving</h3>
        <div className="movement-pad">
          {MOVEMENT_BUTTONS.map(([action, symbol, label], index) => (
            action ? (
              <button
                type="button"
                className={`movement-button ${action === 'stop' ? 'stop' : ''}`}
                key={action}
                disabled={commandDisabled}
                onClick={() => send(action)}
                title={label}
                aria-label={label}
              >
                <strong>{symbol}</strong>
                <span>{label}</span>
              </button>
            ) : <span key={`moving-empty-${index}`} />
          ))}
        </div>
      </div>

      <div className="robot-control-group">
        <h3>Actions</h3>
        <div className="robot-action-buttons">
          <button
            type="button"
            className={`button ${polishingActive ? 'danger' : 'secondary'}`}
            disabled={!configured || Boolean(busyAction) || (!polishingReady && !polishingActive)}
            onClick={() => setShowPolishingDialog(true)}
          >
            {polishingActive ? 'Crankshaft running' : 'Crankshaft polishing'}
          </button>
          <button
            type="button"
            className="button secondary"
            disabled={actionUnavailable || !canLieToStand}
            onClick={() => send('lie_to_stand')}
            title="Available in zero torque or damping mode (FSM 0 or 1)"
          >
            {busyAction === 'lie_to_stand' ? 'Starting…' : 'Lie to stand'}
          </button>
          <button
            type="button"
            className="button secondary"
            disabled={actionUnavailable || !canStandToLie}
            onClick={() => send('stand_to_lie')}
            title="Available in locomotion mode (FSM 811 or 816)"
          >
            {busyAction === 'stand_to_lie' ? 'Starting…' : 'Stand to lie'}
          </button>
        </div>
        <p className="mode-detail">
          Lie to stand requires FSM 0 or 1. Stand to lie requires FSM 811 or 816.
        </p>

        {polishingActive && (
          <p className="mode-detail">
            Polishing with {status.polishing_arm} hand(s) at{' '}
            {status.polishing_speed_deg_s}°/s, holding {status.polishing_hold_seconds} s.
          </p>
        )}
        {!polishingActive && isLocomotionMode && !polishingReady && (
          <p className="mode-detail">Crankshaft polishing requires locomotion FSM 811.</p>
        )}
        <p className="mode-detail">
          Open Crankshaft polishing to view its settings or stop the action.
        </p>
      </div>

      {showPolishingDialog && (
        <div className="control-dialog-backdrop" role="presentation">
          <div
            className="control-dialog polishing-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="polishing-dialog-title"
          >
            <p className="eyebrow">ARM ACTION</p>
            <h3 id="polishing-dialog-title">Crankshaft polishing</h3>
            <p>
              Select the working hand, movement speed, and hold time at each end pose.
            </p>

            <div className="polishing-options" aria-disabled={polishingActive}>
              <label>
                <span>Hands</span>
                <select
                  value={polishingArm}
                  disabled={polishingActive || Boolean(busyAction)}
                  onChange={(event) => setPolishingArm(event.target.value)}
                >
                  <option value="left">Left</option>
                  <option value="right">Right</option>
                  <option value="both">Both</option>
                </select>
              </label>
              <label>
                <span>Speed <strong>{polishingSpeed}°/s</strong></span>
                <SliderSizes
                  ariaLabel="Polishing speed"
                  min={100}
                  max={150}
                  step={5}
                  value={Number(polishingSpeed)}
                  disabled={polishingActive || Boolean(busyAction)}
                  onChange={setPolishingSpeed}
                />
              </label>
              <label>
                <span>Hold time <strong>{Number(polishingHold).toFixed(2)} s</strong></span>
                <SliderSizes
                  ariaLabel="Polishing hold time"
                  min={0.05}
                  max={0.5}
                  step={0.05}
                  value={Number(polishingHold)}
                  disabled={polishingActive || Boolean(busyAction)}
                  onChange={setPolishingHold}
                />
              </label>
            </div>

            {polishingActive && (
              <p className="polishing-running-detail">
                Running with {status.polishing_arm} hand(s) at{' '}
                {status.polishing_speed_deg_s}°/s with a{' '}
                {status.polishing_hold_seconds} s hold.
              </p>
            )}
            <p className="polishing-note">
              Left mirrors the recorded right-hand trajectory. Both moves the two
              arms together.
            </p>

            <div className="control-dialog-actions">
              <button
                type="button"
                className="button secondary"
                disabled={Boolean(busyAction)}
                onClick={() => setShowPolishingDialog(false)}
              >
                Close
              </button>
              <button
                type="button"
                className={`button ${polishingActive ? 'danger' : 'primary'}`}
                disabled={Boolean(busyAction) || (!polishingActive && !polishingReady)}
                onClick={togglePolishing}
              >
                {busyAction === 'crankshaft_start'
                  ? 'Starting…'
                  : busyAction === 'crankshaft_stop'
                    ? 'Stopping…'
                    : polishingActive
                      ? 'Stop polishing'
                      : 'Start polishing'}
              </button>
            </div>
          </div>
        </div>
      )}

      {!configured && (
        <p className="battery-detail">Robot network is not configured.</p>
      )}
      {modeError && configured && (
        <p className="mode-detail">{modeError}</p>
      )}
      {controlError && <p className="error-message">{controlError}</p>}
      {confirmStance && (
        <div className="control-dialog-backdrop" role="presentation">
          <div
            className="control-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="stance-warning-title"
          >
            <p className="eyebrow">SAFETY WARNING</p>
            <h3 id="stance-warning-title">
              Please support the robot before turning to stance mode.
            </h3>
            <p>
              The robot may lose active balance while switching out of locomotion.
            </p>
            <div className="control-dialog-actions">
              <button
                type="button"
                className="button secondary"
                onClick={() => setConfirmStance(false)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="button primary"
                onClick={confirmStanceMode}
              >
                Enter stance mode
              </button>
            </div>
          </div>
        </div>
      )}
      {confirmEnable && (
        <div className="control-dialog-backdrop" role="presentation">
          <div
            className="control-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="control-warning-title"
          >
            <p className="eyebrow">SAFETY WARNING</p>
            <h3 id="control-warning-title">
              Please make sure the robot is standing on clear ground.
            </h3>
            <p>
              Enabling locomotion allows the robot to move immediately when a
              direction button is pressed.
            </p>
            <div className="control-dialog-actions">
              <button
                type="button"
                className="button secondary"
                onClick={() => setConfirmEnable(false)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="button primary"
                onClick={confirmLocomotion}
              >
                Sure, let&apos;s start
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  )
}
