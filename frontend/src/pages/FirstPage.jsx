import { useCallback, useRef, useState } from 'react'
import { BatteryStatus } from '../components/BatteryStatus'
import { RobotSpeechPanel } from '../components/RobotSpeechPanel'
import { RobotControlPanel } from '../components/RobotControlPanel'
import { RobotLedPanel } from '../components/RobotLedPanel'
import { setRobotVolume, speakOnRobot } from '../services/api'

export function FirstPage() {
  const speechRequestBusy = useRef(false)
  const [speechBusy, setSpeechBusy] = useState(false)
  const [speechMessage, setSpeechMessage] = useState(null)
  const [lastSpoken, setLastSpoken] = useState('')
  const [volume, setVolume] = useState(50)
  const [volumeBusy, setVolumeBusy] = useState(false)

  const speak = useCallback(async (text) => {
    const normalized = text.trim()
    if (!normalized || speechRequestBusy.current) return false
    speechRequestBusy.current = true
    setSpeechBusy(true)
    setSpeechMessage(null)
    try {
      const result = await speakOnRobot(normalized)
      setLastSpoken(result.text)
      setSpeechMessage({ type: 'success', text: 'Speech completed.' })
      return true
    } catch (error) {
      setSpeechMessage({ type: 'error', text: error.message })
      return false
    } finally {
      speechRequestBusy.current = false
      setSpeechBusy(false)
    }
  }, [])

  const applyVolume = useCallback(async () => {
    setVolumeBusy(true)
    setSpeechMessage(null)
    try {
      const result = await setRobotVolume(volume)
      setSpeechMessage({ type: 'success', text: `Robot volume set to ${result.volume}%.` })
    } catch (error) {
      setSpeechMessage({ type: 'error', text: error.message })
    } finally {
      setVolumeBusy(false)
    }
  }, [volume])

  return (
    <div className="first-page">
      <section className="workspace-grid">
        <BatteryStatus />
        <div className="console-column">
          <div className="panel speech-panel">
            <RobotSpeechPanel
              busy={speechBusy}
              message={speechMessage}
              lastSpoken={lastSpoken}
              onSpeak={speak}
              volume={volume}
              volumeBusy={volumeBusy}
              onVolumeChange={setVolume}
              onVolumeApply={applyVolume}
            />
          </div>
          <RobotLedPanel />
        </div>
        <RobotControlPanel />
      </section>
    </div>
  )
}
