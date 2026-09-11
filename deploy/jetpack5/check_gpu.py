"""Run from the repository root after JetPack 5 installation; no robot actions."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def main():
    import numpy as np
    import torch
    import torchvision
    from ultralytics import YOLOWorld
    from backend.robot_stereo_detection import RobotStereoDetectionService, _set_model_classes

    print("Python:", sys.executable, sys.version)
    print("PyTorch:", torch.__version__, "CUDA:", torch.version.cuda)
    print("torchvision:", torchvision.__version__)
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA unavailable: check the JetPack-specific torch installation")
    print("GPU:", torch.cuda.get_device_name(0))
    boxes = torch.tensor([[0., 0., 10., 10.], [1., 1., 9., 9.]], device="cuda:0")
    scores = torch.tensor([0.9, 0.8], device="cuda:0")
    kept = torchvision.ops.nms(boxes, scores, 0.5)
    assert kept.cpu().tolist() == [0], "CUDA NMS failed"
    print("CUDA NMS passed")

    service = RobotStereoDetectionService()
    if not service.model_path.is_file():
        raise FileNotFoundError(service.model_path)
    model = YOLOWorld(str(service.model_path))
    model.to("cuda:0")
    _set_model_classes(model, ["person", "chair"], service.source_dir, "cuda:0")
    model.predict(np.zeros((448, 544, 3), dtype=np.uint8), device=0, imgsz=416, verbose=False)
    torch.cuda.synchronize()
    assert next(model.model.parameters()).is_cuda
    print("YOLO-World GPU inference and custom prompts passed")

    from backend.main import app
    assert "/api/robot/stereo/start" in app.openapi()["paths"]
    print("FastAPI schema passed; no robot commands were sent")


if __name__ == "__main__":
    main()
