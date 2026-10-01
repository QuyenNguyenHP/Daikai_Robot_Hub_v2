import { BatteryStatus } from '../components/BatteryStatus'
import { RobotSpeechPanel } from '../components/RobotSpeechPanel'
import { RobotControlPanel } from '../components/RobotControlPanel'
import { RobotLedPanel } from '../components/RobotLedPanel'
import { VideoStreamingPanel } from '../components/VideoStreamingPanel'

const ROBOT_CONVERSATION_ENABLED =
  import.meta.env.VITE_ENABLE_ROBOT_CONVERSATION === 'true'

export function FirstPage() {
  return (
    <div className="first-page">
      <section className="workspace-grid">
        <BatteryStatus />
        <div className="console-column">
          <VideoStreamingPanel />
          {ROBOT_CONVERSATION_ENABLED && <RobotSpeechPanel />}
          <RobotLedPanel />
        </div>
        <RobotControlPanel />
      </section>
    </div>
  )
}
