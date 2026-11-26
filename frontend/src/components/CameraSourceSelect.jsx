import { useState } from 'react'
import { setRobotCameraSource } from '../services/api'

export function CameraSourceSelect({ status, disabled, onStatus, onError }) {
  const [saving, setSaving] = useState(false)
  const changeSource = async (event) => {
    setSaving(true)
    try {
      onStatus(await setRobotCameraSource(event.target.value))
    } catch (error) {
      onError(error.message)
    } finally {
      setSaving(false)
    }
  }
  return (
    <label className="camera-source-select">
      <span>Camera</span>
      <select value={status?.camera_source || 'stereo'} onChange={changeSource}
        disabled={!status || disabled || saving || status?.camera_source_locked}
        title="Stop all camera views and autonomous walking before changing camera">
        <option value="stereo">Robot stereo cameras</option>
        <option value="d415">Intel RealSense D415 (USB)</option>
      </select>
      {saving && <small>Changing camera…</small>}
    </label>
  )
}
