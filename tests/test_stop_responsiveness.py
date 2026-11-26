import threading
import unittest
from unittest.mock import Mock, call, patch

from backend.robot_auto_walk import RobotAutoWalkService
from backend.robot_control import RobotControlService
from backend.robot_stereo_detection import RobotStereoDetectionService


class StopResponsivenessTests(unittest.TestCase):
    def test_releasing_walk_does_not_join_or_stop_visible_camera(self):
        detector = RobotStereoDetectionService()
        detector._active_views.add("depth")
        detector._depth_consumers.add("autonomous_walk")
        detector._thread = Mock()
        detector.release_depth_consumer("autonomous_walk")
        detector._thread.join.assert_not_called()
        self.assertFalse(detector._stop_event.is_set())
        self.assertEqual(detector._active_views, {"depth"})

    def test_releasing_last_consumer_signals_camera_without_join(self):
        detector = RobotStereoDetectionService()
        detector._depth_consumers.add("autonomous_walk")
        detector._thread = Mock()
        detector.release_depth_consumer("autonomous_walk")
        detector._thread.join.assert_not_called()
        self.assertTrue(detector._stop_event.is_set())

    def test_stop_acknowledges_request_without_waiting_for_worker(self):
        walk = RobotAutoWalkService(Mock(), Mock(network_interface="test"))
        walk._thread = Mock()
        walk._thread.is_alive.return_value = True
        status = walk.stop()
        walk._thread.join.assert_not_called()
        self.assertTrue(status["running"])
        self.assertTrue(status["stop_requested"])

    def test_stop_interrupts_movement_wait_and_sends_zero_velocity(self):
        controller = RobotControlService(network_interface="test")
        event = threading.Event()
        client = Mock()

        def velocity(*args):
            event.set()
            return 0

        client.SetVelocity.side_effect = velocity
        with patch.object(controller, "_client_instance", return_value=client), \
             patch.object(controller, "_require_arm_ready"), \
             patch.object(controller, "_require_locomotion"), \
             patch("backend.robot_control.time.sleep", side_effect=AssertionError("Must use interruptible wait")):
            controller.execute_velocity(0.1, 0, 0, 1.0, stop_event=event)
        self.assertEqual(client.SetVelocity.call_args_list, [
            call(0.1, 0, 0, 1.0), call(0.0, 0.0, 0.0, 1.0),
        ])

    def test_stop_requested_before_motion_prevents_velocity_command(self):
        controller = RobotControlService(network_interface="test")
        event = threading.Event()
        event.set()
        client = Mock()
        with patch.object(controller, "_client_instance", return_value=client), \
             patch.object(controller, "_require_arm_ready"), \
             patch.object(controller, "_require_locomotion"):
            result = controller.execute_velocity(0.1, 0, 0, 1.0, stop_event=event)
        client.SetVelocity.assert_not_called()
        self.assertTrue(result["cancelled"])

    def test_restart_while_camera_is_stopping_reports_busy_without_reopening_views(self):
        from backend.robot_stereo_detection import RobotStereoStateError
        detector = RobotStereoDetectionService()
        detector._thread = Mock()
        detector._thread.is_alive.return_value = True
        detector._stop_event.set()
        with self.assertRaisesRegex(RobotStereoStateError, "still stopping"):
            detector.start("depth")
        self.assertEqual(detector._active_views, set())
