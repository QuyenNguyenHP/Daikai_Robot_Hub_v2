import threading
import unittest

from backend.vision_inference import LiveInference


class LiveInferenceTests(unittest.TestCase):
    def test_slow_ai_does_not_block_video_or_queue_old_frames(self):
        worker = LiveInference()
        started, release = threading.Event(), threading.Event()
        calls = []

        def slow(frame):
            calls.append(frame)
            started.set()
            release.wait(2)
            return frame

        try:
            self.assertTrue(worker.submit(slow, "first"))
            self.assertTrue(started.wait(1))
            self.assertIsNone(worker.poll())
            self.assertFalse(worker.submit(slow, "stale"))
            release.set()
            worker.pending.result(timeout=1)
            self.assertEqual(worker.poll(), "first")
            self.assertTrue(worker.submit(slow, "newest"))
            worker.pending.result(timeout=1)
            self.assertEqual(worker.poll(), "newest")
            self.assertEqual(calls, ["first", "newest"])
        finally:
            release.set()
            worker.close()

    def test_failed_inference_can_be_retried(self):
        worker = LiveInference()
        try:
            worker.submit(lambda: 1 / 0)
            with self.assertRaises(ZeroDivisionError):
                worker.pending.result(timeout=1)
            with self.assertRaises(ZeroDivisionError):
                worker.poll()
            self.assertTrue(worker.submit(lambda: "recovered"))
            worker.pending.result(timeout=1)
            self.assertEqual(worker.poll(), "recovered")
        finally:
            worker.close()

    def test_camera_keeps_publishing_while_ai_is_busy(self):
        try:
            import cv2
            import numpy as np
        except ImportError:
            self.skipTest("OpenCV/numpy not installed")
        from unittest.mock import patch
        from backend.robot_stereo_detection import RobotStereoDetectionService
        service = RobotStereoDetectionService()
        service.camera_source = "d415"
        service._active_views.update(("detection", "depth"))
        service._cached_faces = object()
        started, release = threading.Event(), threading.Event()
        test = self

        class Capture:
            count = 0

            def start(self, *, need_depth=False):
                pass

            def read(self, *, need_depth=True):
                self.count += 1
                if self.count == 2:
                    test.assertTrue(started.wait(1))
                    # A first video/depth update was published without waiting for AI.
                    test.assertEqual(service._sequence, 1)
                    test.assertEqual(service._obstacle_distance_m, 2.0)
                    release.set()
                if self.count == 3:
                    service._stop_event.set()
                points = np.zeros((480, 640, 3), np.float32)
                points[:, :, 2] = 2.0
                return np.zeros((480, 640, 3), np.uint8), np.ones((480, 640), np.float32), points

            def stop(self):
                release.set()

        def slow_ai(*args):
            started.set()
            release.wait(2)
            return [], [], 0.0, __import__("time").monotonic()

        try:
            with patch("backend.realsense_camera.D415Capture", Capture), \
                 patch.object(service, "_detection_model", return_value=object()), \
                 patch.object(service, "_infer_frame", side_effect=slow_ai), \
                 patch.object(service, "_load_common", side_effect=AssertionError("RTP not used")), \
                 patch.object(cv2, "imencode", wraps=cv2.imencode) as encode:
                service._run()
            self.assertIsNone(service._error)
            self.assertEqual(service._sequence, 3)
            self.assertIsNotNone(service._frames["detection"])
            self.assertEqual(encode.call_count, 6)
        finally:
            release.set()

    def test_console_rgb_only_does_not_compute_depth(self):
        import numpy as np
        from unittest.mock import patch
        from backend.robot_stereo_detection import RobotStereoDetectionService
        service = RobotStereoDetectionService()
        service.camera_source = "d415"
        service._active_views.add("detection")
        service._cached_faces = object()
        test = self

        class Capture:
            def start(self, *, need_depth=False):
                pass

            def read(self, *, need_depth=True):
                test.assertFalse(need_depth)
                service._stop_event.set()
                return np.full((720, 1280, 3), 150, np.uint8), None, None

            def stop(self):
                pass

        with patch("backend.realsense_camera.D415Capture", Capture), \
             patch.object(service, "_detection_model", return_value=object()), \
             patch.object(service, "_infer_frame", return_value=([], [], 0.0, 0.0)), \
             patch("backend.robot_stereo_detection._depth_heatmap") as heatmap:
            service._run()
        self.assertIsNone(service._error)
        self.assertIsNotNone(service._frames["detection"])
        self.assertEqual(service._frame_size, (1280, 720))
        self.assertEqual(service._depth_sequence, 0)
        self.assertIsNone(service._obstacle_distance_m)
        heatmap.assert_not_called()
