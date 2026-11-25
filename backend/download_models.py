"""Download the OpenCV face models used by Vision."""
from pathlib import Path
import os
import requests


def main():
    target = Path(os.getenv("VISION_FACE_MODELS_DIR", str(Path(__file__).resolve().parent / "models")))
    target.mkdir(parents=True, exist_ok=True)
    for folder, filename in (
        ("face_detection_yunet", "face_detection_yunet_2023mar.onnx"),
        ("face_recognition_sface", "face_recognition_sface_2021dec.onnx"),
    ):
        destination = target / filename
        if destination.is_file():
            continue
        url = f"https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/{folder}/{filename}"
        response = requests.get(url, timeout=60)
        response.raise_for_status()
        temporary = destination.with_suffix(".download")
        temporary.write_bytes(response.content)
        temporary.replace(destination)
        print(f"Saved {destination}")


if __name__ == "__main__":
    main()
