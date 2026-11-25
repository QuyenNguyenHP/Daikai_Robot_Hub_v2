"""Console telemetry and person-only Vision behavior without robot hardware."""
import math
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from backend.robot_imu import RobotIMUService
from backend.robot_stereo_detection import RobotStereoDetectionService, RobotStereoError


class ConsoleTests(unittest.TestCase):
    def test_battery_exposes_actual_cell_voltages_for_monitor(self):
        from backend.robot_battery import RobotBatteryService
        service = RobotBatteryService(network_interface="test-interface")
        service._handle_message(SimpleNamespace(
            bmsvoltage=[48600, 0], cell_vol=[3740, 3730, 3750, 0],
            temperature=[30, 32, 0], current=-3200, soc=82, soh=95,
            cycle=20, version_high=1, version_low=2))
        result = service.status()
        self.assertTrue(result['connected'])
        self.assertEqual(result['battery']['cell_voltages_v'], [3.74, 3.73, 3.75])
        self.assertEqual(result['battery']['cell_count'], 3)
        self.assertEqual(result['battery']['balance_mv'], 20)
        self.assertEqual(result['battery']['charge_state'], 'DISCHARGING')

    def test_imu_units_and_stale_status(self):
        service = RobotIMUService(network_interface="eth-test")
        message = SimpleNamespace(imu_state=SimpleNamespace(
            rpy=[math.pi / 2, 0, -math.pi], gyroscope=[1, 2, 3],
            accelerometer=[0, 0, 9.81], quaternion=[1, 0, 0, 0], temperature=28))
        service._handle_message(message)
        status = service.status()
        self.assertTrue(status['connected'])
        self.assertNotIn('battery', status)
        self.assertEqual(status['imu']['rpy_deg'], [90, 0, -180])
        self.assertEqual(status['imu']['gyroscope_rad_s'], [1, 2, 3])
        self.assertEqual(status['imu']['accelerometer_m_s2'], [0, 0, 9.81])
        self.assertEqual(status['imu']['quaternion_wxyz'], [1, 0, 0, 0])
        service._last_update_at = time.time() - 11
        self.assertFalse(service.status()['connected'])
        self.assertEqual(service.status()['state'], 'stale')
        message.imu_state.rpy[0] = float('nan')
        service._handle_message(message)
        self.assertEqual(service.status()['message_count'], 1)

    def test_vision_rejects_object_prompts(self):
        service = RobotStereoDetectionService()
        self.assertEqual(service.prompts, ['person'])
        with self.assertRaises(RobotStereoError):
            service.set_classes(['chair'])
        self.assertEqual(service.set_classes(['person'])['classes'], ['person'])

    def test_face_matching_and_unknown(self):
        import numpy as np
        from backend.vision_faces import VisionFaces
        service = VisionFaces.__new__(VisionFaces)
        service.reload_database = Mock()
        service.threshold = 0.363
        service.names = ['Known person']
        service.embeddings = np.eye(1, 128, dtype=np.float32)
        service.detector = Mock()
        service.detector.detect.return_value = (None, [np.array([10, 20, 30, 40])])
        service.recognizer = Mock()
        service.recognizer.feature.return_value = np.eye(1, 128, dtype=np.float32)
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        self.assertEqual(service.recognize(frame)[0]['name'], 'Known person')
        service.recognizer.feature.return_value = -np.eye(1, 128, dtype=np.float32)
        self.assertEqual(service.recognize(frame)[0]['name'], 'Unknown')
        service.names = []
        self.assertEqual(service.recognize(frame)[0]['name'], 'Unknown')
        service.detector.detect.return_value = (None, None)
        self.assertEqual(service.recognize(frame), [])


if __name__ == '__main__':
    unittest.main()
