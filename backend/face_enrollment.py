"""Photo enrollment for the same database used by live Vision recognition."""
import re
import threading

from backend.face_database import DATABASE_LOCK, database_path, load_database, save_database

MAX_FILES = 10
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_UPLOAD_BYTES = 25 * 1024 * 1024


class FaceEnrollmentError(ValueError):
    pass


class FaceEnrollmentService:
    def __init__(self):
        self._lock = threading.Lock()
        self._vision = None

    @staticmethod
    def normalize_name(name):
        normalized = " ".join(name.split())
        if (not normalized or len(normalized) > 80 or normalized in {".", ".."}
                or re.search(r"[/\\\x00-\x1f\x7f]", normalized)):
            raise FaceEnrollmentError("Enter a name of 1–80 characters without slashes or control characters.")
        return normalized

    def people(self):
        with DATABASE_LOCK:
            names, _ = load_database(database_path())
        return {"people": [{"name": name, "embeddings": names.count(name)} for name in sorted(set(names), key=str.casefold)]}

    def enroll(self, raw_name, images):
        import cv2
        import numpy as np
        from backend.vision_faces import VisionFaces

        name = self.normalize_name(raw_name)
        if not 1 <= len(images) <= MAX_FILES:
            raise FaceEnrollmentError(f"Select between 1 and {MAX_FILES} photos.")
        if sum(len(payload) for _, payload in images) > MAX_UPLOAD_BYTES:
            raise FaceEnrollmentError("The total upload must be at most 25 MB.")
        with self._lock:
            if self._vision is None:
                self._vision = VisionFaces()
            accepted, rejected, features = [], [], []
            for filename, payload in images:
                try:
                    if not payload or len(payload) > MAX_IMAGE_BYTES:
                        raise FaceEnrollmentError("Photo must be non-empty and at most 5 MB.")
                    frame = cv2.imdecode(np.frombuffer(payload, dtype=np.uint8), cv2.IMREAD_COLOR)
                    if frame is None:
                        raise FaceEnrollmentError("Photo could not be decoded.")
                    height, width = frame.shape[:2]
                    if width * height > 20_000_000:
                        raise FaceEnrollmentError("Photo must be at most 20 megapixels.")
                    scale = min(1.0, 1280 / max(width, height))
                    if scale < 1:
                        frame = cv2.resize(frame, (max(1, round(width * scale)), max(1, round(height * scale))))
                    height, width = frame.shape[:2]
                    self._vision.detector.setInputSize((width, height))
                    _, faces = self._vision.detector.detect(frame)
                    if faces is None or len(faces) == 0:
                        raise FaceEnrollmentError("No face found. Use a clear, well-lit photo.")
                    if len(faces) != 1:
                        raise FaceEnrollmentError("Multiple faces found. Use a photo of one person.")
                    aligned = self._vision.recognizer.alignCrop(frame, faces[0])
                    feature = self._vision.recognizer.feature(aligned).flatten().astype(np.float32)
                    norm = np.linalg.norm(feature)
                    if feature.shape != (128,) or not np.isfinite(feature).all() or norm < 1e-6:
                        raise FaceEnrollmentError("Could not extract a usable face embedding.")
                    features.append(feature / norm)
                    accepted.append(filename)
                except (FaceEnrollmentError, cv2.error) as error:
                    rejected.append({"file": filename, "reason": str(error)})
            if features:
                with DATABASE_LOCK:
                    path = database_path()
                    names, embeddings = load_database(path)
                    # Append samples; existing people and their samples are preserved.
                    names.extend([name] * len(features))
                    embeddings = np.concatenate((embeddings, np.stack(features)), axis=0)
                    save_database(path, names, embeddings)
            return {"name": name, "saved": bool(features), "accepted": len(accepted),
                    "accepted_files": accepted, "rejected": rejected,
                    "message": "Registration saved. Vision reloads the face database automatically." if features else "No photos were accepted. Registration was not saved."}
