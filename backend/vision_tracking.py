"""Short-lived optical-flow boxes between asynchronous AI results."""
import time


class FlowBoxes:
    def __init__(self):
        self.tracks = []
        self.gray = None
        self.updated_at = 0.0

    @staticmethod
    def grayscale(frame):
        import cv2
        return cv2.resize(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), None,
                          fx=0.5, fy=0.5)

    def reset(self, frame, items, now):
        import cv2
        import numpy as np
        self.gray = self.grayscale(frame)
        self.tracks = []
        for box, payload in items:
            x1, y1, x2, y2 = (int(v / 2) for v in box)
            mask = np.zeros_like(self.gray)
            mask[max(0, y1):y2, max(0, x1):x2] = 255
            points = cv2.goodFeaturesToTrack(self.gray, 32, 0.01, 3, mask=mask)
            if points is not None:
                self.tracks.append((np.asarray(box, dtype=float), payload, points))
        self.updated_at = now

    def advance(self, frame, now=None):
        import cv2
        import numpy as np
        now = time.monotonic() if now is None else now
        gray = self.grayscale(frame)
        if now - self.updated_at > 2.0 or self.gray is None or self.gray.shape != gray.shape:
            self.tracks = []
        active = []
        for box, payload, points in self.tracks:
            moved, status, _ = cv2.calcOpticalFlowPyrLK(self.gray, gray, points, None)
            if moved is None:
                continue
            back, back_status, _ = cv2.calcOpticalFlowPyrLK(gray, self.gray, moved, None)
            if back is None:
                continue
            valid = ((status.ravel() == 1) & (back_status.ravel() == 1)
                     & (np.linalg.norm(back - points, axis=2).ravel() < 1.5))
            if valid.sum() < 3:
                continue
            delta = np.median((moved - points)[valid, 0], axis=0) * 2
            box = box + np.tile(delta, 2)
            height, width = frame.shape[:2]
            box[[0, 2]] = np.clip(box[[0, 2]], 0, width - 1)
            box[[1, 3]] = np.clip(box[[1, 3]], 0, height - 1)
            if box[2] <= box[0] or box[3] <= box[1]:
                continue
            active.append((box, payload, moved[valid].reshape(-1, 1, 2)))
        self.tracks, self.gray = active, gray
        return [(tuple(int(v) for v in box), payload) for box, payload, _ in active]
