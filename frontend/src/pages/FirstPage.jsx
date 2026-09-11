import { BatteryStatus } from '../components/BatteryStatus'
import { RobotSpeechPanel } from '../components/RobotSpeechPanel'
import { RobotControlPanel } from '../components/RobotControlPanel'
import { RobotLedPanel } from '../components/RobotLedPanel'
import { VideoStreamingPanel } from '../components/VideoStreamingPanel'

export function FirstPage() {
  return (
    <div className="first-page">
      <section className="workspace-grid">
        <BatteryStatus />
        <div className="console-column">
          <VideoStreamingPanel />
          <RobotSpeechPanel />
          <RobotLedPanel />
        </div>
        <RobotControlPanel />
      </section>
    </div>
  )
}
