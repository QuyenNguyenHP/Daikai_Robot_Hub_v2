import { useId } from 'react'

export function TelemetryChart({ samples, metric, color, unit, now }) {
  const id = useId().replace(/:/g, '')
  const points = samples.filter((point) => point.time >= now - 60000)
  const values = points.map((point) => point[metric]).filter(Number.isFinite)
  const min = values.length ? Math.min(...values) : 0
  const max = values.length ? Math.max(...values) : 1
  const padding = Math.max((max - min) * 0.15, metric === 'temperature' ? 0.5 : 0.1)
  const low = min - padding
  const high = max + padding
  let path = ''
  let previous = null
  for (const point of points) {
    if (!Number.isFinite(point[metric])) { previous = null; continue }
    const x = Math.max(0, Math.min(600, (point.time - now + 60000) / 100))
    const y = 70 - (point[metric] - low) / (high - low) * 64
    const move = !previous || point.time - previous.time > 2500
    path += `${move ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)} `
    previous = point
  }
  return (
    <div className="telemetry-chart">
      <div className="chart-scale"><span>{values.length ? high.toFixed(1) : '—'} {unit}</span><span>{values.length ? low.toFixed(1) : '—'} {unit}</span></div>
      <svg viewBox="0 0 600 78" preserveAspectRatio="none" role="img" aria-label={`${metric} history, last 60 seconds in ${unit}`}>
        <defs><pattern id={id} width="100" height="24" patternUnits="userSpaceOnUse"><path d="M 100 0 L 0 0 0 24" fill="none" stroke="#1c3350" strokeWidth="1" /></pattern></defs>
        <rect width="600" height="78" fill={`url(#${id})`} />
        <path d={path} fill="none" stroke={color} strokeWidth="2" vectorEffect="non-scaling-stroke" />
      </svg>
      {!values.length && <span className="chart-empty">Waiting for telemetry</span>}
    </div>
  )
}
