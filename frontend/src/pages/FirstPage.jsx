import { TextToSpeechPanel } from '../components/TextToSpeechPanel'
import { RobotActionsPanel } from '../components/RobotActionsPanel'
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
        <div className="console-column">
          <VideoStreamingPanel />
          {ROBOT_CONVERSATION_ENABLED && <RobotSpeechPanel />}
          <TextToSpeechPanel />
          <RobotLedPanel />
        </div>
        <div className="console-column">
          <RobotControlPanel />
          <RobotActionsPanel />
        </div>
      </section>
    </div>
  )
}
