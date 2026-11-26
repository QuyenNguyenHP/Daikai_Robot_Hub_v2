import threading
import unittest
from unittest.mock import patch

from backend.robot_stereo_detection import (
    RobotStereoDetectionService, RobotStereoError, RobotStereoStateError,
)


class CameraSourceTests(unittest.TestCase):
    def test_d415_depth_does_not_require_robot_calibration(self):
        service = RobotStereoDetectionService()
        service.set_camera_source("d415")
        with patch("backend.robot_stereo_detection.importlib.util.find_spec", return_value=object()):
            self.assertIsNone(service._configuration_error("depth"))
        with patch("backend.robot_stereo_detection.importlib.util.find_spec", return_value=None):
            self.assertIn("pyrealsense2", service._configuration_error("depth"))

    def test_switch_rejects_active_depth_consumer(self):
        service = RobotStereoDetectionService()
        service._depth_consumers.add("autonomous_walk")
        with self.assertRaises(RobotStereoStateError):
            service.set_camera_source("d415")
        self.assertEqual(service.camera_source, "stereo")

    def test_switch_rejects_running_worker(self):
        service = RobotStereoDetectionService()
        service._thread = threading.current_thread()
        with self.assertRaises(RobotStereoStateError):
            service.set_camera_source("d415")

    def test_switch_clears_old_depth_and_frames(self):
        service = RobotStereoDetectionService()
        service._obstacle_distance_m = 2.0
        service._frames["depth"] = b"old frame"
        service._last_frame_at = 123
        service.set_camera_source("d415")
        self.assertIsNone(service._obstacle_distance_m)
        self.assertIsNone(service._frames["depth"])
        self.assertIsNone(service._last_frame_at)
        with self.assertRaises(RobotStereoError):
            service.set_camera_source("unknown")

    def test_camera_source_api_validation_and_walking_guard(self):
        from types import SimpleNamespace
        from fastapi.testclient import TestClient
        from backend.main import app
        from unittest.mock import Mock
        service = RobotStereoDetectionService()
        previous = {}
        replacements = {
            "camera_start_lock": threading.Lock(),
            "robot_stereo_detection": service,
            "robot_auto_walk": SimpleNamespace(status=Mock(return_value={"running": False})),
        }
        for name, value in replacements.items():
            previous[name] = getattr(app.state, name, None)
            setattr(app.state, name, value)
        try:
            client = TestClient(app)
            response = client.post("/api/robot/stereo/camera-source", json={"source": "d415"})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["camera_source"], "d415")
            self.assertEqual(client.post("/api/robot/stereo/camera-source",
                                         json={"source": "bad"}).status_code, 422)
            replacements["robot_auto_walk"].status.return_value = {"running": True}
            self.assertEqual(client.post("/api/robot/stereo/camera-source",
                                         json={"source": "stereo"}).status_code, 409)
            self.assertEqual(service.camera_source, "d415")
        finally:
            for name, value in previous.items():
                if value is None:
                    delattr(app.state, name)
                else:
                    setattr(app.state, name, value)
