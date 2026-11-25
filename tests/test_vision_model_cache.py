"""Model reuse and invalidation without loading CUDA or starting robot video."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from backend.robot_stereo_detection import RobotStereoDetectionService


class VisionModelCacheTests(unittest.TestCase):
    def test_restart_reuses_prepared_model_and_device_name(self):
        with tempfile.TemporaryDirectory() as directory:
            service = RobotStereoDetectionService()
            service.model_path = Path(directory) / 'model.pt'
            service.model_path.write_bytes(b'weights')
            model = object()
            service._device_name = 'Test GPU'
            service._create_detection_model = Mock(return_value=model)
            self.assertIs(service._detection_model(), model)
            # A restarted stereo worker resets its local model and device label.
            service._device_name = 'depth only'
            self.assertIs(service._detection_model(), model)
            self.assertEqual(service._device_name, 'Test GPU')
            service._create_detection_model.assert_called_once()

    def test_changed_weights_device_or_prompts_invalidate_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            service = RobotStereoDetectionService()
            service.model_path = Path(directory) / 'model.pt'
            service.model_path.write_bytes(b'weights')
            service._create_detection_model = Mock(side_effect=lambda: object())
            original = service._detection_model()
            service.model_path.write_bytes(b'updated weights')
            updated = service._detection_model()
            self.assertIsNot(original, updated)
            service.device = 'cpu'
            cpu = service._detection_model()
            self.assertIsNot(updated, cpu)
            service.prompts = ['PERSON']
            self.assertIsNot(cpu, service._detection_model())
            self.assertEqual(service._create_detection_model.call_count, 4)

    def test_failed_load_is_retriable(self):
        with tempfile.TemporaryDirectory() as directory:
            service = RobotStereoDetectionService()
            service.model_path = Path(directory) / 'model.pt'
            service.model_path.touch()
            model = object()
            service._create_detection_model = Mock(side_effect=[RuntimeError('temporary'), model])
            with self.assertRaises(RuntimeError):
                service._detection_model()
            self.assertIsNone(service._cached_model)
            self.assertIs(service._detection_model(), model)


if __name__ == '__main__':
    unittest.main()
