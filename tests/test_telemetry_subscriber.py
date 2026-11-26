import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from backend.telemetry_subscriber import LatestTelemetrySubscriber
from backend.robot_control import RobotControlService, RobotControlError


class TelemetrySubscriberTests(unittest.TestCase):
    def test_poll_latest_uses_native_depth_one_without_receive_callback(self):
        channel = Mock()
        channel.Read.return_value = "latest"
        factory = Mock()
        factory.CreateChannel.return_value = channel
        qos = Mock(return_value="latest-only-qos")
        history = Mock(return_value="depth-one")
        modules = {
            "unitree_sdk2py.core.channel": SimpleNamespace(ChannelFactory=lambda: factory),
            "cyclonedds.qos": SimpleNamespace(Qos=qos, Policy=SimpleNamespace(
                History=SimpleNamespace(KeepLast=history), Reliability=SimpleNamespace(BestEffort="best-effort"))),
        }
        with patch.dict("sys.modules", modules):
            subscriber = LatestTelemetrySubscriber("rt/lowstate", object)
            received = threading.Event()
            messages = []

            def handle(message):
                messages.append(message)
                subscriber.stop_event.set()
                received.set()

            try:
                subscriber.Init(handle)
                self.assertTrue(received.wait(1))
            finally:
                subscriber.Close()
            subscriber.Close()
        channel.SetReader.assert_called_once_with("latest-only-qos")
        qos.assert_called_once_with("depth-one", "best-effort")
        history.assert_called_once_with(1)
        channel.CloseReader.assert_called_once()
        self.assertEqual(messages, ["latest"])

    def test_timeout_does_not_claim_robot_rejected_command(self):
        with self.assertRaisesRegex(RobotControlError, "outcome is unknown"):
            RobotControlService._require_success(3104, "enter stance mode")
        with self.assertRaisesRegex(RobotControlError, "Robot rejected"):
            RobotControlService._require_success(3204, "enter stance mode")
