import { useEffect, useState } from 'react'

// A missing or stalled socket must never leave the HUD showing old values as live.
export function useRobotTelemetry(url) {
  const [reading, setReading] = useState({ status: null, receivedAt: 0, socketOpen: false })
  const [now, setNow] = useState(Date.now())
  useEffect(() => {
    let active = true
    let socket
    let retry
    let delay = 1000
    const connect = () => {
      socket = new WebSocket(url)
      socket.onopen = () => { delay = 1000 }
      socket.onmessage = (event) => {
        if (!active) return
        try {
          setReading({ status: JSON.parse(event.data), receivedAt: Date.now(), socketOpen: true })
        } catch {
          setReading((value) => ({ ...value, socketOpen: false }))
        }
      }
      socket.onclose = () => {
        if (!active) return
        setReading((value) => ({ ...value, socketOpen: false }))
        retry = window.setTimeout(connect, delay)
        delay = Math.min(delay * 2, 5000)
      }
    }
    connect()
    const clock = window.setInterval(() => setNow(Date.now()), 1000)
    return () => {
      active = false
      window.clearTimeout(retry)
      window.clearInterval(clock)
      if (socket?.readyState < WebSocket.CLOSING) socket.close()
    }
  }, [url])
  const connected = Boolean(reading.socketOpen && reading.status?.connected && now - reading.receivedAt < 3500)
  return { status: reading.status, connected, now }
}
