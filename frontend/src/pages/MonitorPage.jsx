import { useEffect, useState } from 'react'
import { RobotModel } from '../components/RobotModel'
import { TelemetryChart } from '../components/TelemetryChart'
import { useRobotTelemetry } from '../hooks/useRobotTelemetry'
import { getRobotBatteryWebSocketUrl, getRobotIMUWebSocketUrl } from '../services/api'

const display = (value, digits = 2) => Number.isFinite(value) ? value.toFixed(digits) : '—'

function Row({ label, value, unit = '' }) {
  return <div className="hud-row"><span>{label}</span><strong>{value ?? '—'} <small>{unit}</small></strong></div>
}

function Axes({ values, labels = ['X', 'Y', 'Z'], unit = '' }) {
  return <div className="hud-trio">{labels.map((label, index) => <div key={label}><span>{label}</span><strong>{display(values?.[index], 2)}<small>{unit}</small></strong></div>)}</div>
}

export default function MonitorPage() {
  const batteryFeed = useRobotTelemetry(getRobotBatteryWebSocketUrl())
  const imuFeed = useRobotTelemetry(getRobotIMUWebSocketUrl())
  const [samples, setSamples] = useState([])
  const [clock, setClock] = useState(Date.now())
  const battery = batteryFeed.connected ? batteryFeed.status?.battery : null
  const imu = imuFeed.connected ? imuFeed.status?.imu : null
  const connected = batteryFeed.connected && imuFeed.connected
  const partial = batteryFeed.connected || imuFeed.connected

  useEffect(() => {
    const timer = window.setInterval(() => setClock(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [])

  useEffect(() => {
    const value = batteryFeed.status?.battery
    const time = value?.updated_at ? value.updated_at * 1000 : Date.now()
    if (!batteryFeed.connected || !value || Date.now() - time > 10000) return
    setSamples((history) => {
      if (history.at(-1)?.time === time) return history
      return [...history.filter((sample) => sample.time > Date.now() - 60000), {
        time, voltage: value.voltage_v, current: value.current_a, temperature: value.max_temperature_c,
      }].slice(-120)
    })
  }, [batteryFeed.status, batteryFeed.connected])

  const cells = battery?.cell_voltages_v || []
  const minimum = cells.length ? Math.min(...cells) : 0

  return (
    <div className="monitor-page">
      <section className="panel monitor-heading">
        <div><p className="eyebrow">UNITREE R1 · ROBOT TELEMETRY</p><h1>Live HUD <span>Robot monitor</span></h1></div>
        <div className="monitor-heading-right">
          <time>{new Date(clock).toLocaleTimeString('en-GB', { timeZone: 'Asia/Singapore' })}<small>SGT</small></time>
          <span className={`status-pill ${connected ? 'live' : ''}`}><i />{connected ? 'Telemetry live' : partial ? 'Partial signal' : 'No signal'}</span>
        </div>
      </section>

      <div className="monitor-grid">
        <section className={`panel hud-battery ${battery ? '' : 'hud-disconnected'}`} aria-label="Battery telemetry">
          <div className="hud-card-heading"><p className="eyebrow">POWER SYSTEM</p><span className={`hud-source ${battery ? 'online' : ''}`}>{battery ? '● LIVE' : '○ OFFLINE'}</span></div>
          <h2>Battery</h2>
          <div className="hud-charge">{display(battery?.charge_percent, 0)}<small>%</small></div>
          <div className="hud-battery-bar" role="meter" aria-label="Battery charge" aria-valuemin={0} aria-valuemax={100} aria-valuenow={battery ? battery.charge_percent : undefined} aria-valuetext={battery ? `${battery.charge_percent}%` : 'No telemetry'}><i style={{ width: `${Math.max(0, Math.min(100, battery?.charge_percent || 0))}%` }} /></div>
          <Row label="Voltage" value={display(battery?.voltage_v)} unit="V" />
          <Row label="Current" value={display(battery?.current_a)} unit="A" />
          <Row label="State" value={battery?.charge_state} />
          <Row label="Temperature max" value={display(battery?.max_temperature_c, 1)} unit="°C" />
          <Row label="Imbalance" value={display(battery?.balance_mv, 0)} unit="mV" />
          <Row label="Health" value={battery?.health} />
          <div className="hud-cells-heading"><p className="eyebrow">CELLS {battery?.cells ? ` / ${battery.cells}` : ''}</p><small>Voltage · V</small></div>
          <div className="hud-cells">
            {cells.map((voltage, index) => <div key={index} title={`Cell ${index + 1}: ${voltage.toFixed(3)} V`}><i className={voltage === minimum ? 'lowest' : ''} style={{ height: `${Math.max(8, Math.min(100, voltage / 4.3 * 100))}%` }} /><span>{index + 1}</span></div>)}
            {!cells.length && <span className="hud-empty">Waiting for cell telemetry</span>}
          </div>
          <p className="hud-note">{batteryFeed.status?.error || (batteryFeed.connected ? 'Live BMS telemetry' : 'Waiting for battery signal…')}</p>
        </section>

        <RobotModel imu={imu} connected={Boolean(imu)} />

        <section className={`panel hud-imu ${imu ? '' : 'hud-disconnected'}`} aria-label="IMU telemetry">
          <div className="hud-card-heading"><p className="eyebrow">INERTIAL MEASUREMENT</p><span className={`hud-source ${imu ? 'online' : ''}`}>{imu ? '● LIVE' : '○ OFFLINE'}</span></div>
          <h2>Orientation</h2>
          <Axes values={imu?.rpy_deg} labels={['Roll', 'Pitch', 'Yaw']} unit="°" />
          <p className="eyebrow hud-section-label">ANGULAR VELOCITY <small>rad/s</small></p>
          <Axes values={imu?.gyroscope_rad_s} />
          <p className="eyebrow hud-section-label">ACCELERATION <small>m/s²</small></p>
          <Axes values={imu?.accelerometer_m_s2} />
          <p className="eyebrow hud-section-label">QUATERNION <small>W / X / Y / Z</small></p>
          <div className="hud-quaternion">{['W', 'X', 'Y', 'Z'].map((axis, index) => <div key={axis}><span>{axis}</span><strong>{display(imu?.quaternion_wxyz?.[index], 3)}</strong></div>)}</div>
          <Row label="IMU temperature" value={display(imu?.temperature_c, 1)} unit="°C" />
          <p className="hud-note">{imuFeed.status?.error || (imuFeed.connected ? 'Live body attitude · 5 Hz updates' : 'Waiting for IMU signal…')}</p>
        </section>
      </div>

      <section className="panel hud-history" aria-label="Battery telemetry history">
        <div className="history-heading"><p className="eyebrow">TELEMETRY HISTORY / LAST 60 SECONDS</p><span>Independent scales · live readings only</span></div>
        <div className="history-charts">
          {[['voltage', 'Voltage', 'V', '#4fc3f7'], ['current', 'Current', 'A', '#3ddc97'], ['temperature', 'Temperature', '°C', '#ffb547']].map(([metric, label, unit, color]) => <div key={metric}><h3><i style={{ background: color }} />{label}</h3><TelemetryChart samples={samples} metric={metric} color={color} unit={unit} now={clock} /></div>)}
        </div>
        <div className="history-times"><span>−60 s</span><span>NOW</span></div>
      </section>
    </div>
  )
}
