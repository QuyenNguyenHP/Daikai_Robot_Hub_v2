const API_URL = (import.meta.env.VITE_API_URL || window.location.origin).replace(/\/$/, '')
const WS_BASE_URL = (
  import.meta.env.VITE_WS_URL
  || (import.meta.env.DEV
    ? `${window.location.protocol}//${window.location.hostname}:8010`
    : API_URL)
).replace(/\/$/, '')

function webSocketUrl(path) {
  const url = new URL(path, WS_BASE_URL)
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
  return url.toString()
}

async function request(path, options = {}) {
  const { timeoutMs = 30000, ...fetchOptions } = options
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  try {
    const response = await fetch(`${API_URL}${path}`, { ...fetchOptions, signal: controller.signal })
    const payload = await response.json().catch((error) => {
      if (controller.signal.aborted) throw error
      return {}
    })
    if (!response.ok) {
      const detail = payload.detail
      const message = typeof detail === 'string'
        ? detail
        : detail?.message || `Request failed (${response.status})`
      throw new Error(message)
    }
    return payload
  } catch (error) {
    if (controller.signal.aborted) {
      throw new Error('No response from backend. The action may still be pending; check the live status before retrying.')
    }
    throw error
  } finally {
    clearTimeout(timer)
  }
}

export const getHealth = () => request('/api/health')

export const getRobotBattery = () => request('/api/robot/battery')

export function getRobotBatteryWebSocketUrl() {
  return webSocketUrl('/api/robot/battery/ws')
}

export const getRobotControlStatus = () => request('/api/robot/control/status')

export function getRobotControlStatusWebSocketUrl() {
  return webSocketUrl('/api/robot/control/status/ws')
}

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
  return webSocketUrl('/api/robot/mode/ws')
}

export function controlRobot(action, options = {}) {
  return request('/api/robot/control', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action, ...options }),
  })
}

export function speakOnRobot(text, options = {}) {
  return request('/api/robot/speak', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, ...options }),
  })
}

export const getRobotVoiceChatStatus = () => request('/api/robot/voice-chat/status')

export function sendRobotTextMessage(messages) {
  return request('/api/robot/text-chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ messages }),
  })
}

export function sendRobotVoiceMessage(audio, sessionId) {
  return request('/api/robot/voice-chat', {
    method: 'POST',
    headers: {
      'Content-Type': audio.type || 'application/octet-stream',
      'X-Voice-Session': sessionId,
    },
    body: audio,
  })
}

export function setRobotLed(red, green, blue, keepOn = false) {
  return request('/api/robot/led', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ red, green, blue, keep_on: keepOn }),
  })
}

export const getRobotStereoStatus = () => request('/api/robot/stereo/status')

export function getRobotStereoWebSocketUrl() {
  return webSocketUrl('/api/robot/stereo/ws')
}

export const startRobotStereo = () => (
  request('/api/robot/stereo/start', { method: 'POST' })
)

export const stopRobotStereo = () => (
  request('/api/robot/stereo/stop', { method: 'POST', timeoutMs: 8000 })
)

export const startRobotStereoView = (view) => (
  request(`/api/robot/stereo/start/${view}`, { method: 'POST' })
)

export const stopRobotStereoView = (view) => (
  request(`/api/robot/stereo/stop/${view}`, { method: 'POST', timeoutMs: 8000 })
)

export function setRobotStereoClasses(classes) {
  return request('/api/robot/stereo/classes', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ classes }),
  })
}

export const getRobotStereoStreamUrl = (view, version = 0) => (
  `${API_URL}/api/robot/stereo/stream/${view}?stream_version=${version}`
)

export const getRobotAutoWalkStatus = () => request('/api/robot/auto-walk/status')

export function getRobotAutoWalkWebSocketUrl() {
  return webSocketUrl('/api/robot/auto-walk/ws')
}

export function startRobotAutoWalk(settings) {
  return request('/api/robot/auto-walk/start', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(settings),
  })
}

export const stopRobotAutoWalk = () => (
  request('/api/robot/auto-walk/stop', { method: 'POST', timeoutMs: 8000 })
)

export const getRobotIMUWebSocketUrl = () => webSocketUrl('/api/robot/imu/ws')

export const getRobotArmActions = () => request('/api/robot/arm-actions')

export const executeRobotArmAction = (actionId) => request('/api/robot/arm-actions/execute', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ action_id: actionId }),
})

export const getRobotSpeechStatus = () => request('/api/robot/speech/status')
export const getEnrolledPeople = () => request('/api/vision/people')
export function enrollFace(name, files) {
  const body = new FormData()
  body.append('name', name)
  files.forEach((file) => body.append('images', file))
  return request('/api/vision/enroll', { method: 'POST', body })
}

export const setRobotCameraSource = (source) => request(
  '/api/robot/stereo/camera-source', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ source }) },
)
