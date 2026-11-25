"""Atomic access to the existing local SFace embedding archive."""
import os
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATABASE_LOCK = threading.RLock()


def database_path():
    return Path(os.getenv("VISION_FACE_DATABASE", str(ROOT / "data/embeddings.npz")))


def load_database(path):
    import numpy as np
    if not path.is_file():
        return [], np.empty((0, 128), dtype=np.float32)
    # Legacy archives in this repository store names as a trusted object array.
    with np.load(path, allow_pickle=True) as data:
        names = data["names"].tolist()
        embeddings = data["embeddings"].astype(np.float32)
    if not isinstance(names, list) or embeddings.shape != (len(names), 128):
        raise ValueError("Face database must contain matching names and 128-dimensional embeddings.")
    if not all(isinstance(name, str) for name in names) or not np.isfinite(embeddings).all():
        raise ValueError("Face database contains invalid names or embeddings.")
    return names, embeddings


def save_database(path, names, embeddings):
    import numpy as np
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".npz", delete=False) as file:
            temporary = Path(file.name)
            np.savez_compressed(file, names=np.asarray(names, dtype=str), embeddings=embeddings.astype(np.float32))
            file.flush()
            os.fsync(file.fileno())
        os.replace(str(temporary), str(path))
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
