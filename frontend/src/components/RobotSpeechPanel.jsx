import { useState } from 'react'
import RobotVolumeControl from './RobotVolumeControl'


export function RobotSpeechPanel({
  busy,
  message,
  lastSpoken,
  onSpeak,
  volume,
  volumeBusy,
  onVolumeChange,
  onVolumeApply,
}) {
  const [text, setText] = useState('')

  const submit = async (event) => {
    event.preventDefault()
    const spoken = await onSpeak(text)
    if (spoken) setText('')
  }

  return (
    <div className="panel speech-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">ROBOT VOICE</p>
          <h2>Make the robot speak</h2>
        </div>
        <RobotVolumeControl
          value={volume}
          busy={busy || volumeBusy}
          disabled={busy}
          onChange={onVolumeChange}
          onApply={onVolumeApply}
        />
      </div>

      <form className="speech-form" onSubmit={submit}>
        <input
          className="text-input"
          value={text}
          onChange={(event) => setText(event.target.value)}
          placeholder="Type English text for the robot to say"
          maxLength="200"
        />
        <button className="button primary" disabled={busy || !text.trim()}>
          {busy ? 'Speaking…' : 'Speak'}
        </button>
      </form>

      <div className="speech-details">
        <span>Send English text directly to the robot speaker.</span>
        {lastSpoken && <strong>Last spoken: “{lastSpoken}”</strong>}
      </div>
      {message && (
        <p className={message.type === 'error' ? 'error-message' : 'success-message'}>
          {message.text}
        </p>
      )}
    </div>
  )
}
