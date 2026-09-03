const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

async function request(path, options = {}) {
  const response = await fetch(`${API_URL}${path}`, options)
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = payload.detail
    const message = typeof detail === 'string'
      ? detail
      : detail?.message || `Request failed (${response.status})`
    throw new Error(message)
  }
  return payload
}

export const getHealth = () => request('/api/health')

export const getRobotBattery = () => request('/api/robot/battery')

export function getRobotBatteryWebSocketUrl() {
  const url = new URL('/api/robot/battery/ws', API_URL)
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
  return url.toString()
}

export const getRobotControlStatus = () => request('/api/robot/control/status')

export const getVideoStreamStatus = () => request('/api/video-stream/status')

export function startVideoStream() {
  return request('/api/video-stream/start', {
    method: 'POST',
  })
}

export function getVideoStreamFeedUrl() {
  return `${API_URL}/api/video-stream/feed`
}

export function stopVideoStream() {
  return request('/api/video-stream/stop', { method: 'POST' })
}

export const getRobotServices = () => request('/api/robot/services')

export function switchRobotService(name, enabled) {
  return request('/api/robot/services/switch', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, enabled }),
  })
}

export const getTeleoperationStatus = () => request('/api/robot/teleoperation/status')

export function startTeleoperation(inputMode) {
  return request('/api/robot/teleoperation/start', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ input_mode: inputMode }),
  })
}

export function startTeleoperationTracking() {
  return request('/api/robot/teleoperation/tracking/start', { method: 'POST' })
}

export function stopTeleoperation() {
  return request('/api/robot/teleoperation/stop', { method: 'POST' })
}

export const getRobotMode = () => request('/api/robot/mode')

export function getRobotModeWebSocketUrl() {
  const url = new URL('/api/robot/mode/ws', API_URL)
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
  return url.toString()
}

export function controlRobot(action, options = {}) {
  return request('/api/robot/control', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action, ...options }),
  })
}

export function speakOnRobot(text) {
  return request('/api/robot/speak', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  })
}

export function setRobotLed(red, green, blue, keepOn = false) {
  return request('/api/robot/led', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ red, green, blue, keep_on: keepOn }),
  })
}
