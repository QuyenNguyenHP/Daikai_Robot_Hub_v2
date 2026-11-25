"""YuNet/SFace recognition using the hub's existing local face database."""
import os
from pathlib import Path

from backend.face_database import DATABASE_LOCK, database_path, load_database


ROOT = Path(__file__).resolve().parents[1]


class VisionFaces:
    def __init__(self):
        import cv2

        models = Path(os.getenv("VISION_FACE_MODELS_DIR", str(ROOT / "backend/models")))
        detector = models / "face_detection_yunet_2023mar.onnx"
        recognizer = models / "face_recognition_sface_2021dec.onnx"
        if not detector.is_file() or not recognizer.is_file():
            raise FileNotFoundError(
                "Face models missing. Run python3 -m backend.download_models "
                "or set VISION_FACE_MODELS_DIR."
            )
        self.detector = cv2.FaceDetectorYN.create(str(detector), "", (544, 448), 0.9, 0.3, 5000)
        self.recognizer = cv2.FaceRecognizerSF.create(str(recognizer), "")
        self.threshold = float(os.getenv("VISION_FACE_THRESHOLD", "0.363"))
        if not 0 <= self.threshold <= 1:
            raise ValueError("VISION_FACE_THRESHOLD must be between 0 and 1.")
        self.database = database_path()
        self._database_version = None
        self.reload_database()

    def reload_database(self):
        import numpy as np
        with DATABASE_LOCK:
            version = self.database.stat().st_mtime_ns if self.database.is_file() else 0
            if version == self._database_version:
                return
            names, embeddings = load_database(self.database)
            norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
            normalized = np.divide(embeddings, norms, out=np.zeros_like(embeddings), where=norms != 0)
            self.names, self.embeddings = names, normalized
            self._database_version = version

    def recognize(self, frame):
        import numpy as np

        self.reload_database()
        height, width = frame.shape[:2]
        self.detector.setInputSize((width, height))
        _, faces = self.detector.detect(frame)
        results = []
        for face in faces if faces is not None else []:
            feature = self.recognizer.feature(self.recognizer.alignCrop(frame, face)).flatten()
            norm = np.linalg.norm(feature)
            name, score = "Unknown", 0.0
            if self.names and norm > 0:
                scores = self.embeddings @ (feature / norm)
                best = int(np.argmax(scores))
                score = float(scores[best])
                if score >= self.threshold:
                    name = str(self.names[best])
            x, y, w, h = [int(v) for v in face[:4]]
            results.append({"name": name, "confidence": round(score, 4),
                            "box": [max(0, x), max(0, y), min(width, x+w), min(height, y+h)]})
        return results
