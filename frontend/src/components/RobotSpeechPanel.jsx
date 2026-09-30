import { useEffect, useRef, useState } from 'react'
import { getRobotVoiceChatStatus, sendRobotTextMessage } from '../services/api'


export function RobotSpeechPanel() {
  const conversationRef = useRef(null)
  const [configured, setConfigured] = useState(null)
  const [conversation, setConversation] = useState([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState(null)

  useEffect(() => {
    getRobotVoiceChatStatus()
      .then((status) => setConfigured(Boolean(status.configured)))
      .catch(() => setConfigured(false))
  }, [])

  useEffect(() => {
    const element = conversationRef.current
    if (element) element.scrollTop = element.scrollHeight
  }, [conversation, busy])

  const submitMessage = async (event) => {
    event.preventDefault()
    const text = input.trim()
    if (!text || busy) return

    const userMessage = { role: 'user', content: text }
    const messages = [
      ...conversation.map((item) => ({ role: item.role, content: item.text })),
      userMessage,
    ].slice(-30)

    setConversation((items) => [...items, { role: 'user', text }])
    setInput('')
    setBusy(true)
    setMessage({ type: 'info', text: 'AI is preparing a reply…' })

    try {
      const result = await sendRobotTextMessage(messages)
      setConversation((items) => [
        ...items,
        { role: 'assistant', text: result.text },
      ])
      setMessage({
        type: 'success',
        text: 'The reply was sent to the robot speaker.',
      })
    } catch (error) {
      setMessage({ type: 'error', text: error.message })
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="panel speech-panel">
      <div className="panel-heading voice-heading">
        <div>
          <p className="eyebrow">VOICE AI</p>
          <h2>Conversation with robot</h2>
        </div>
        <span className={`status-pill ${configured ? 'live' : ''}`}>
          <i /> {configured ? 'AI configured' : 'AI unavailable'}
        </span>
      </div>

      <div className="voice-conversation" ref={conversationRef} aria-live="polite">
        {conversation.length === 0 && (
          <div className="voice-empty">
            <strong>Start a conversation</strong>
            <span>Type a message. The reply will appear here and play through the robot.</span>
          </div>
        )}
        {conversation.map((item, index) => (
          <div className={`voice-message ${item.role}`} key={`${item.role}-${index}`}>
            <small>{item.role === 'user' ? 'You' : 'Robot'}</small>
            <p>{item.text}</p>
          </div>
        ))}
        {busy && (
          <div className="voice-message assistant pending">
            <small>Robot</small>
            <p>Thinking…</p>
          </div>
        )}
      </div>

      <form className="voice-chat-form" onSubmit={submitMessage}>
        <input
          className="text-input"
          type="text"
          value={input}
          maxLength={10000}
          disabled={busy || configured === false}
          placeholder="Type a message to the robot…"
          aria-label="Message to robot"
          onChange={(event) => setInput(event.target.value)}
        />
        <button
          className="button primary"
          type="submit"
          disabled={busy || configured === false || !input.trim()}
        >
          {busy ? 'Sending…' : 'Send'}
        </button>
      </form>

      {message && (
        <p className={message.type === 'error' ? 'error-message' : 'success-message'}>
          {message.text}
        </p>
      )}
    </section>
  )
}
