import { HudIcon } from './HudIcon'
import { useEffect, useRef, useState } from 'react'
import { getRobotSpeechStatus, speakOnRobot } from '../services/api'

export function TextToSpeechPanel() {
  const [text, setText] = useState('')
  const [volume, setVolume] = useState(70)
  const [status, setStatus] = useState(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState(null)
  const inFlight = useRef(false)

  useEffect(() => {
    let active = true
    const refresh = () => getRobotSpeechStatus().then((value) => { if (active) setStatus(value) }).catch(() => { if (active) setStatus(null) })
    refresh()
    const timer = window.setInterval(refresh, 5000)
    return () => { active = false; window.clearInterval(timer) }
  }, [])

  const submit = async (event) => {
    event.preventDefault()
    if (!text.trim() || inFlight.current) return
    inFlight.current = true
    setBusy(true)
    setMessage(null)
    try {
      await speakOnRobot(text.trim(), { volume: Number(volume) })
      setMessage({ type: 'success', text: 'Speech request accepted by the robot.' })
    } catch (error) {
      setMessage({ type: 'error', text: error.message })
    } finally {
      inFlight.current = false
      setBusy(false)
    }
  }
  const available = Boolean(status?.available)
  return (
    <section className="panel tts-panel" aria-labelledby="tts-title">
      <div className="panel-heading">
        <div><p className="eyebrow">ROBOT VOICE</p><h2 id="tts-title"><HudIcon name="volume" /> Text to Speech</h2></div>
        <span className={`status-pill ${available ? 'live' : ''}`}><i />{busy ? 'Sending…' : available ? 'Configured' : 'Unavailable'}</span>
      </div>
      <p className="tts-description">Type a message for the robot to say using its built-in voice.</p>
      <form onSubmit={submit} className="tts-form">
        <label htmlFor="tts-text" className="field-label">Message</label>
        <textarea id="tts-text" rows={4} maxLength={200} value={text} onChange={(event) => setText(event.target.value)} placeholder="Hello, I am R1. Nice to meet you!" disabled={busy} required />
        <span className="tts-counter">{text.length} / 200</span>
        <div className="tts-options">
          <label htmlFor="tts-volume">Volume <strong>{volume}%</strong><input id="tts-volume" type="range" min="0" max="100" value={volume} disabled={busy} onChange={(event) => setVolume(Number(event.target.value))} /></label>
        </div>
        <button type="submit" className="button primary" disabled={!available || status?.busy || busy || !text.trim()}><HudIcon name="volume" />{busy ? 'Sending…' : 'Speak on robot'}</button>
      </form>
      <p className="mode-detail">Uses the robot’s default voice. Language support depends on the firmware.</p>
      <div aria-live="polite">{message && <p className={`${message.type}-message`}>{message.text}</p>}</div>
    </section>
  )
}
