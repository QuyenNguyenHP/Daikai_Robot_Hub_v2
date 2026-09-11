import { useEffect, useRef, useState } from 'react'
import { getRobotVoiceChatStatus, sendRobotVoiceMessage } from '../services/api'


const MAX_RECORDING_MS = 30_000


function recordingMimeType() {
  const options = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4']
  return options.find((type) => window.MediaRecorder?.isTypeSupported(type)) || ''
}


export function RobotSpeechPanel() {
  const recorderRef = useRef(null)
  const streamRef = useRef(null)
  const chunksRef = useRef([])
  const stopTimerRef = useRef(null)
  const sessionIdRef = useRef(window.crypto?.randomUUID?.() || `robot-${Date.now()}`)
  const [recording, setRecording] = useState(false)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState(null)
  const [configured, setConfigured] = useState(null)
  const [conversation, setConversation] = useState([])

  const releaseMicrophone = () => {
    streamRef.current?.getTracks().forEach((track) => track.stop())
    streamRef.current = null
  }

  useEffect(() => {
    getRobotVoiceChatStatus()
      .then((status) => setConfigured(Boolean(status.configured)))
      .catch(() => setConfigured(false))
    return () => {
      if (stopTimerRef.current) window.clearTimeout(stopTimerRef.current)
      if (recorderRef.current?.state === 'recording') {
        recorderRef.current.onstop = null
        recorderRef.current.stop()
      }
      releaseMicrophone()
    }
  }, [])

  const submitRecording = async (blob) => {
    if (!blob.size) {
      setMessage({ type: 'error', text: 'No microphone audio was recorded.' })
      return
    }
    setBusy(true)
    setMessage({ type: 'info', text: 'AI is listening and preparing a reply…' })
    try {
      const result = await sendRobotVoiceMessage(blob, sessionIdRef.current)
      setConversation((items) => [
        ...items,
        { role: 'user', text: result.transcript || 'Voice message' },
        { role: 'assistant', text: result.text || 'Audio response played.' },
      ])
      setMessage({
        type: 'success',
        text: `Reply played through the robot (${result.duration_seconds}s).`,
      })
    } catch (error) {
      setMessage({ type: 'error', text: error.message })
    } finally {
      setBusy(false)
    }
  }

  const startRecording = async () => {
    setMessage(null)
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      setMessage({ type: 'error', text: 'This browser cannot record microphone audio.' })
      return
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream
      chunksRef.current = []
      const mimeType = recordingMimeType()
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined)
      recorderRef.current = recorder
      recorder.ondataavailable = (event) => {
        if (event.data.size) chunksRef.current.push(event.data)
      }
      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, {
          type: recorder.mimeType || 'application/octet-stream',
        })
        chunksRef.current = []
        releaseMicrophone()
        setRecording(false)
        submitRecording(blob)
      }
      recorder.start(250)
      setRecording(true)
      stopTimerRef.current = window.setTimeout(() => recorder.stop(), MAX_RECORDING_MS)
    } catch (error) {
      releaseMicrophone()
      setMessage({
        type: 'error',
        text: error.name === 'NotAllowedError'
          ? 'Microphone permission was denied.'
          : `Could not start microphone: ${error.message}`,
      })
    }
  }

  const stopRecording = () => {
    if (stopTimerRef.current) window.clearTimeout(stopTimerRef.current)
    stopTimerRef.current = null
    if (recorderRef.current?.state === 'recording') recorderRef.current.stop()
  }

  return (
    <section className="panel speech-panel">
      <div className="panel-heading voice-heading">
        <div>
          <p className="eyebrow">VOICE AI</p>
          <h2>Talk with the robot</h2>
        </div>
        <span className={`status-pill ${configured ? 'live' : ''}`}>
          <i /> {configured ? 'AI configured' : 'AI unavailable'}
        </span>
      </div>

      <div className="voice-conversation" aria-live="polite">
        {conversation.length === 0 && (
          <div className="voice-empty">
            <strong>Start a conversation</strong>
            <span>Record a question. The AI response will play through the robot.</span>
          </div>
        )}
        {conversation.map((item, index) => (
          <div className={`voice-message ${item.role}`} key={`${item.role}-${index}`}>
            <small>{item.role === 'user' ? 'You' : 'Robot'}</small>
            <p>{item.text}</p>
          </div>
        ))}
      </div>

      <div className="voice-actions">
        {recording ? (
          <button className="button danger voice-recording" type="button" onClick={stopRecording}>
            <i /> Stop and send
          </button>
        ) : (
          <button
            className="button primary"
            type="button"
            disabled={busy || configured === false}
            onClick={startRecording}
          >
            {busy ? 'Waiting for AI…' : 'Record question'}
          </button>
        )}
        <span>{recording ? 'Listening… maximum 30 seconds' : 'Uses your browser microphone'}</span>
      </div>
      {message && (
        <p className={message.type === 'error' ? 'error-message' : 'success-message'}>
          {message.text}
        </p>
      )}
    </section>
  )
}
