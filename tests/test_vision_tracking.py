import unittest

import cv2
import numpy as np

from backend.vision_tracking import FlowBoxes


class FlowBoxesTests(unittest.TestCase):
    def test_box_follows_motion_and_expires_without_fresh_ai(self):
        frame = np.zeros((240, 320, 3), np.uint8)
        texture = np.random.RandomState(7).randint(0, 256, (80, 80, 3), dtype=np.uint8)
        frame[60:140, 80:160] = texture
        tracker = FlowBoxes()
        tracker.reset(frame, [((80, 60, 160, 140), "person")], 10.0)
        moved = cv2.warpAffine(frame, np.float32([[1, 0, 12], [0, 1, 8]]), (320, 240))
        boxes = tracker.advance(moved, 10.1)
        self.assertEqual(len(boxes), 1)
        np.testing.assert_allclose(boxes[0][0], (92, 68, 172, 148), atol=2)
        self.assertEqual(boxes[0][1], "person")
        self.assertEqual(len(tracker.advance(moved, 11.5)), 1)
        self.assertEqual(tracker.advance(moved, 12.1), [])

    def test_lost_features_do_not_leave_a_frozen_box(self):
        frame = np.random.RandomState(3).randint(0, 256, (240, 320, 3), dtype=np.uint8)
        tracker = FlowBoxes()
        tracker.reset(frame, [((80, 60, 160, 140), "face")], 10.0)
        tracker.advance(np.zeros_like(frame), 10.1)
        self.assertEqual(tracker.advance(np.zeros_like(frame), 10.2), [])
