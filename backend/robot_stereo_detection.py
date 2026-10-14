"""Web-facing YOLO-World object detection and stereo distance service."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import importlib.util
import os
import sys
import threading
import time
from pathlib import Path
from typing import Iterator



BACKEND_DIR = Path(__file__).resolve().parent
REFERENCE_DIR = BACKEND_DIR / "r1_yolo_world_stereo"
DEFAULT_CLASSES = "person,chair,bottle,cup,table,door,box"

# ---------------------------------------------------------------------------
# USER SETTINGS — CENTER CLEARANCE REGION (PIXELS)
# X and Y are the top-left corner. WIDTH and HEIGHT are the box size.
# The default stereo frame is 544 x 448 pixels.
# ---------------------------------------------------------------------------
CENTER_CLEARANCE_X = 300
CENTER_CLEARANCE_Y = 180
CENTER_CLEARANCE_WIDTH = 220
CENTER_CLEARANCE_HEIGHT = 260

# Nearest reliable obstacle calculation. The region is split into local cells;
# cells with too little valid stereo depth are ignored as likely noise.
CENTER_CLEARANCE_CELL_SIZE_PX = 16
CENTER_CLEARANCE_MIN_VALID_RATIO = 0.40

DETECTION_COLORS = (
    (80, 220, 120),
    (255, 180, 70),
    (80, 190, 255),
    (220, 100, 255),
    (70, 230, 230),
    (255, 120, 120),
    (180, 120, 255),
    (120, 255, 210),
)


class RobotStereoError(RuntimeError):
    """Raised when the stereo detection pipeline cannot be controlled."""


class RobotStereoStateError(RobotStereoError):
    """Raised when configuration changes require the pipeline to be stopped."""


def _set_model_classes(model, prompts, source_dir, device) -> None:
    """Set YOLO-World prompts across supported Ultralytics releases.

    Newer releases provide ``ultralytics.nn.text_model`` and let us redirect
    their CLIP cache. Ultralytics 8.3 uses OpenAI CLIP directly instead.
    """
    try:
        from ultralytics.nn import text_model
    except ImportError:
        try:
            import clip
        except ImportError as exc:
            raise RobotStereoError(
                "YOLO-World needs the CLIP package for object prompts. Install it with: "
                "python -m pip install 'git+https://github.com/openai/CLIP.git'"
            ) from exc
        clip_path = source_dir / "weights" / "clip" / "ViT-B-32.pt"
        clip_model, _ = clip.load(
            str(clip_path) if clip_path.is_file() else "ViT-B/32",
            device=device,
            download_root=str(clip_path.parent),
        )
        model.model.clip_model = clip_model
    else:
        text_model.WEIGHTS_DIR = source_dir / "weights"
    model.set_classes(prompts)


def _env_int(name: str, default: int, minimum: int = 1) -> int:
    try:
        return max(minimum, int(os.getenv(name, str(default))))
    except ValueError:
        return default


def _env_float(name: str, default: float, minimum: float = 0.0) -> float:
    try:
        return max(minimum, float(os.getenv(name, str(default))))
    except ValueError:
        return default


def _object_distance(
    points_3d: np.ndarray,
    disparity: np.ndarray,
    box: tuple[int, int, int, int],
    inner_scale: float,
    min_distance_m: float,
    max_distance_m: float,
    mode: str,
) -> float | None:
    """Use the robust inner-box median calculation from the reference script."""
    x1, y1, x2, y2 = box
    center_x = (x1 + x2) / 2.0
    center_y = (y1 + y2) / 2.0
    half_width = max(2.0, (x2 - x1) * inner_scale / 2.0)
    half_height = max(2.0, (y2 - y1) * inner_scale / 2.0)
    inner_x1 = max(0, int(center_x - half_width))
    inner_y1 = max(0, int(center_y - half_height))
    inner_x2 = min(points_3d.shape[1], int(center_x + half_width) + 1)
    inner_y2 = min(points_3d.shape[0], int(center_y + half_height) + 1)

    roi_points = points_3d[inner_y1:inner_y2, inner_x1:inner_x2]
    roi_disparity = disparity[inner_y1:inner_y2, inner_x1:inner_x2]
    distances = (
        np.linalg.norm(roi_points, axis=2)
        if mode == "euclidean"
        else roi_points[:, :, 2]
    )
    valid = (
        np.isfinite(distances)
        & (roi_disparity > 0.5)
        & (distances >= min_distance_m)
        & (distances <= max_distance_m)
    )
    samples = distances[valid]
    if samples.size < 20:
        return None
    low, high = np.percentile(samples, (10, 90))
    trimmed = samples[(samples >= low) & (samples <= high)]
    return float(np.median(trimmed)) if trimmed.size >= 10 else None


def _disparity_preview(disparity: np.ndarray, num_disparities: int) -> np.ndarray:
    normalized = np.clip(disparity / float(num_disparities), 0.0, 1.0)
    preview = cv2.applyColorMap(
        (normalized * 255.0).astype(np.uint8), cv2.COLORMAP_TURBO
    )
    preview[disparity <= 0.5] = (20, 20, 20)
    return preview


def _region_distance(
    points_3d: np.ndarray,
    disparity: np.ndarray,
    region: tuple[float, float, float, float],
    min_distance_m: float,
    max_distance_m: float,
    mode: str,
    percentile: float = 10.0,
    cell_size_px: int = CENTER_CLEARANCE_CELL_SIZE_PX,
    min_valid_ratio: float = CENTER_CLEARANCE_MIN_VALID_RATIO,
) -> float | None:
    """Return the nearest reliable local surface in the image region."""
    height, width = disparity.shape[:2]
    x1 = max(0, min(width - 1, int(width * region[0])))
    y1 = max(0, min(height - 1, int(height * region[1])))
    x2 = max(x1 + 1, min(width, int(width * region[2])))
    y2 = max(y1 + 1, min(height, int(height * region[3])))
    roi_points = points_3d[y1:y2, x1:x2]
    roi_disparity = disparity[y1:y2, x1:x2]
    distances = (
        np.linalg.norm(roi_points, axis=2)
        if mode == "euclidean"
        else roi_points[:, :, 2]
    )
    valid = (
        np.isfinite(distances)
        & (roi_disparity > 0.5)
        & (distances >= min_distance_m)
        & (distances <= max_distance_m)
    )
    samples = distances[valid]
    if samples.size < 100:
        return None

    # A raw minimum is easily corrupted by one mismatched stereo pixel. Use
    # the nearest median from a sufficiently populated local cell instead.
    cell_distances = []
    roi_height, roi_width = distances.shape
    for cell_y in range(0, roi_height, cell_size_px):
        for cell_x in range(0, roi_width, cell_size_px):
            cell_y2 = min(roi_height, cell_y + cell_size_px)
            cell_x2 = min(roi_width, cell_x + cell_size_px)
            cell_valid = valid[cell_y:cell_y2, cell_x:cell_x2]
            if (
                cell_valid.size == 0
                or np.count_nonzero(cell_valid) < cell_valid.size * min_valid_ratio
            ):
                continue
            cell_values = distances[cell_y:cell_y2, cell_x:cell_x2][cell_valid]
            cell_distances.append(float(np.median(cell_values)))

    if cell_distances:
        return min(cell_distances)
    return float(np.percentile(samples, percentile))


class RobotStereoDetectionService:
    """Run one shared stereo/YOLO pipeline and retain two newest JPEG views."""

    def __init__(self, *, enable_object_detection: bool = True) -> None:
        self.enable_object_detection = enable_object_detection
        self.source_dir = Path(os.getenv("R1_STEREO_SOURCE_DIR", str(REFERENCE_DIR)))
        self.calibration_path = Path(
            os.getenv(
                "R1_STEREO_CALIBRATION",
                str(self.source_dir / "r1_stereo_calibration.npz"),
            )
        )
        self.model_path = Path(
            os.getenv(
                "R1_YOLO_WORLD_MODEL",
                str(self.source_dir / "yolov8s-worldv2.pt"),
            )
        )
        self.prompts = [item.strip() for item in DEFAULT_CLASSES.split(",")]
        self.left_port = _env_int("R1_STEREO_LEFT_PORT", 5002)
        self.right_port = _env_int("R1_STEREO_RIGHT_PORT", 5003)
        self.width = _env_int("R1_STEREO_WIDTH", 544)
        self.height = _env_int("R1_STEREO_HEIGHT", 448)
        self.capture_backend = os.getenv("R1_STEREO_CAPTURE_BACKEND", "auto")
        self.confidence = min(_env_float("R1_YOLO_CONFIDENCE", 0.25), 1.0)
        self.image_size = _env_int("R1_YOLO_IMAGE_SIZE", 416)
        self.detect_every = _env_int("R1_YOLO_DETECT_EVERY", 2)
        self.device = os.getenv("R1_YOLO_DEVICE", "cuda:0").strip() or "cuda:0"
        self._device_name = None
        self.num_disparities = _env_int("R1_STEREO_NUM_DISPARITIES", 64, 16)
        self.num_disparities = max(16, (self.num_disparities // 16) * 16)
        self.block_size = _env_int("R1_STEREO_BLOCK_SIZE", 3, 3)
        if self.block_size % 2 == 0:
            self.block_size += 1
        self.inner_scale = min(_env_float("R1_STEREO_INNER_SCALE", 0.4), 1.0)
        self.min_distance_m = _env_float("R1_STEREO_MIN_DISTANCE_M", 0.15)
        self.max_distance_m = _env_float("R1_STEREO_MAX_DISTANCE_M", 15.0)
        self.max_pair_delta_ms = _env_float("R1_STEREO_MAX_PAIR_DELTA_MS", 80.0)
        self.distance_mode = os.getenv("R1_STEREO_DISTANCE_MODE", "z")
        if self.distance_mode not in {"z", "euclidean"}:
            self.distance_mode = "z"
        # Normalized left, top, right, bottom bounds of the forward corridor.
        # Keeping the bottom of the image out reduces floor-triggered turns.
        # Keep the corridor away from the less reliable left/right overlap
        # boundaries of the stereo pair. It remains centered on the robot's
        # forward travel direction.
        self.obstacle_region = (
            CENTER_CLEARANCE_X / self.width,
            CENTER_CLEARANCE_Y / self.height,
            (CENTER_CLEARANCE_X + CENTER_CLEARANCE_WIDTH) / self.width,
            (CENTER_CLEARANCE_Y + CENTER_CLEARANCE_HEIGHT) / self.height,
        )
        self.obstacle_percentile = min(
            50.0, _env_float("R1_STEREO_OBSTACLE_PERCENTILE", 10.0)
        )
        self.disparity_consistency_px = _env_float(
            "R1_STEREO_DISPARITY_CONSISTENCY_PX", 2.0
        )

        self._condition = threading.Condition()
        self._active_views: set[str] = set()
        self._depth_consumers: set[str] = set()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._frames: dict[str, bytes | None] = {"detection": None, "depth": None}
        self._sequence = 0
        self._state = "stopped"
        self._error: str | None = None
        self._last_frame_at: float | None = None
        self._detections: list[dict[str, object]] = []
        self._fps = 0.0
        self._stereo_ms = 0.0
        self._yolo_ms = 0.0
        self._pair_delta_ms = 0.0
        self._baseline_m: float | None = None
        self._obstacle_distance_m: float | None = None

    def _configuration_error(self, view: str | None = None) -> str | None:
        if (
            CENTER_CLEARANCE_X < 0
            or CENTER_CLEARANCE_Y < 0
            or CENTER_CLEARANCE_WIDTH < 1
            or CENTER_CLEARANCE_HEIGHT < 1
            or CENTER_CLEARANCE_X + CENTER_CLEARANCE_WIDTH > self.width
            or CENTER_CLEARANCE_Y + CENTER_CLEARANCE_HEIGHT > self.height
        ):
            return (
                "CENTER_CLEARANCE_X/Y/WIDTH/HEIGHT must define a positive region "
                f"inside the {self.width}x{self.height} stereo frame."
            )
        common_path = self.source_dir / "r1_stereo_common.py"
        if not common_path.is_file():
            return f"Stereo reference module not found: {common_path}"
        if not self.calibration_path.is_file():
            return f"Stereo calibration not found: {self.calibration_path}"
        needs_detection = self.enable_object_detection and view != "depth"
        if needs_detection and not self.model_path.is_file():
            return f"YOLO-World model not found: {self.model_path}"
        if needs_detection and not self.prompts:
            return "R1_YOLO_WORLD_CLASSES must contain at least one class."
        return None

    def start(self, view: str | None = None, *, visible: bool = True) -> None:
        with self._condition:
            if view not in (None, "detection", "depth"):
                raise RobotStereoError(f"Unknown stereo view: {view}")
            if visible:
                self._active_views.update(("detection", "depth") if view is None else (view,))
            if self._thread is not None and self._thread.is_alive():
                self._condition.notify_all()
                return
            error = self._configuration_error(view)
            if error:
                self._state = "error"
                self._error = error
                raise RobotStereoError(error)
            self._frames = {"detection": None, "depth": None}
            self._detections = []
            self._last_frame_at = None
            self._fps = self._stereo_ms = self._yolo_ms = self._pair_delta_ms = 0.0
            self._device_name = None
            self._obstacle_distance_m = None
            self._stop_event.clear()
            self._state = "loading"
            self._error = None
            self._thread = threading.Thread(
                target=self._run, name="r1-stereo-detection", daemon=True
            )
            self._thread.start()

    def stop(self, view: str | None = None) -> None:
        with self._condition:
            if view is not None:
                self._active_views.discard(view)
                self._frames[view] = None
                if self._active_views:
                    self._condition.notify_all()
                    return
            else:
                self._active_views.clear()
            if self._depth_consumers:
                self._condition.notify_all()
                return
        self._stop_event.set()
        with self._condition:
            self._condition.notify_all()

    def acquire_depth_consumer(self, name: str) -> None:
        with self._condition:
            self._depth_consumers.add(name)
        try:
            self.start("depth", visible=False)
        except Exception:
            with self._condition:
                self._depth_consumers.discard(name)
            raise

    def release_depth_consumer(self, name: str) -> None:
        with self._condition:
            self._depth_consumers.discard(name)
            should_stop = not self._depth_consumers and not self._active_views
        if should_stop:
            self.stop()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=30.0)
        with self._condition:
            if thread is not None and thread.is_alive():
                self._state = "stopping"
                self._error = "Stereo detection is still stopping; try again shortly."
            else:
                self._state = "stopped"
                self._error = None
            self._condition.notify_all()

    def set_classes(self, prompts: list[str]) -> dict[str, object]:
        normalized = []
        seen = set()
        for prompt in prompts:
            value = prompt.strip()
            key = value.casefold()
            if not value or key in seen:
                continue
            if len(value) > 80:
                raise RobotStereoError("Each object prompt must be 80 characters or less.")
            seen.add(key)
            normalized.append(value)
        if not normalized:
            raise RobotStereoError("Enter at least one object to detect.")
        if len(normalized) > 30:
            raise RobotStereoError("A maximum of 30 object prompts is supported.")

        with self._condition:
            if self._thread is not None and self._thread.is_alive():
                raise RobotStereoStateError(
                    "Stop stereo detection before changing object prompts."
                )
            self.prompts = normalized
            self._detections = []
            self._error = None
        return self.status()

    def _load_common(self):
        path = self.source_dir / "r1_stereo_common.py"
        module_name = "r1_web_stereo_common"
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise RobotStereoError(f"Could not load stereo helpers from {path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module

    def _set_terminal_error(self, message: str) -> None:
        with self._condition:
            self._state = "error"
            self._error = message
            self._condition.notify_all()

    def _run(self) -> None:
        capture = None
        try:
            global cv2, np
            import cv2
            import numpy as np

            common = self._load_common()
            geometry = common.StereoGeometry(self.calibration_path)
            matcher = common.create_sgbm(self.num_disparities, self.block_size)
            model = None

            def load_detection_model():
                import torch

                device = torch.device(
                    "cuda:" + self.device if self.device.isdigit() else self.device
                )
                if device.type not in {"cuda", "cpu"}:
                    raise RobotStereoError(
                        "R1_YOLO_DEVICE must be cuda:0, a GPU index, or cpu."
                    )
                if device.type == "cuda" and not torch.cuda.is_available():
                    raise RobotStereoError(
                        "CUDA is unavailable. Install a CUDA-enabled PyTorch build matching "
                        "your JetPack and Python versions. CPU is only used if "
                        "R1_YOLO_DEVICE=cpu."
                    )
                self._device_name = (
                    torch.cuda.get_device_name(device)
                    if device.type == "cuda"
                    else "CPU"
                )
                try:
                    from ultralytics import YOLOWorld
                except ImportError as exc:
                    raise RobotStereoError(
                        "Could not import Ultralytics in the Python environment running "
                        f"the backend: {exc}"
                    ) from exc
                loaded_model = YOLOWorld(str(self.model_path))
                loaded_model.to(device)
                _set_model_classes(loaded_model, self.prompts, self.source_dir, device)
                return loaded_model

            self._device_name = "depth only"
            capture = common.StereoRtpCapture(
                self.left_port,
                self.right_port,
                width=self.width,
                height=self.height,
                backend=self.capture_backend,
            )
            capture.start()
            with self._condition:
                self._state = "waiting"
                self._baseline_m = round(float(geometry.baseline_m), 4)
        except Exception as exc:
            self._set_terminal_error(f"Could not start stereo detection: {exc}")
            if capture is not None:
                capture.stop()
            return

        def compute_depth(left, right):
            started = time.monotonic()
            disparity = common.compute_disparity(matcher, left, right)
            # Reject isolated SGBM mismatches. These commonly appear as false
            # near-depth patches in dark/low-texture areas and near occlusion
            # boundaries, especially on the left side of the disparity map.
            local_median = cv2.medianBlur(disparity, 5)
            locally_consistent = (
                (disparity > 0.5)
                & (local_median > 0.5)
                & (np.abs(disparity - local_median) <= self.disparity_consistency_px)
            )
            disparity = np.where(locally_consistent, local_median, -1.0).astype(
                np.float32
            )
            points = geometry.points_from_disparity(disparity)
            return disparity, points, (time.monotonic() - started) * 1000.0

        depth_worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="stereo-depth")
        previous_time = time.monotonic()
        frame_index = 0
        cached_detections: list[tuple[int, int, int, int, str, float]] = []
        last_yolo_ms = 0.0
        try:
            while not self._stop_event.is_set():
                with self._condition:
                    detection_active = "detection" in self._active_views
                if detection_active and model is None:
                    with self._condition:
                        self._state = "loading"
                    model = load_detection_model()
                try:
                    left, right, pair_delta_ms = capture.read_pair(
                        timeout_s=2.0,
                        max_delta_ms=self.max_pair_delta_ms,
                    )
                except TimeoutError as exc:
                    with self._condition:
                        self._state = "waiting"
                        self._error = str(exc)
                    continue

                processing_started = time.monotonic()
                left_rectified, right_rectified = geometry.rectify(left, right)
                # Stereo CPU work overlaps GPU inference on the same rectified pair.
                depth_future = depth_worker.submit(
                    compute_depth, left_rectified, right_rectified
                )
                rectify_ms = (time.monotonic() - processing_started) * 1000.0
                annotated = left_rectified.copy()

                if detection_active and model is not None and frame_index % self.detect_every == 0:
                    options = {
                        "conf": self.confidence,
                        "imgsz": self.image_size,
                        "verbose": False,
                    }
                    if self.device is not None:
                        options["device"] = self.device
                    yolo_started = time.monotonic()
                    result = model.predict(left_rectified, **options)[0]
                    last_yolo_ms = (time.monotonic() - yolo_started) * 1000.0
                    cached_detections = []
                    # Transfer all boxes once instead of synchronizing CUDA per field.
                    for detection in result.boxes.data.detach().cpu().tolist():
                        x1, y1, x2, y2 = (int(value) for value in detection[:4])
                        x1 = max(0, min(annotated.shape[1] - 1, x1))
                        y1 = max(0, min(annotated.shape[0] - 1, y1))
                        x2 = max(x1 + 1, min(annotated.shape[1], x2))
                        y2 = max(y1 + 1, min(annotated.shape[0], y2))
                        class_id = int(detection[-1])
                        cached_detections.append(
                            (
                                x1,
                                y1,
                                x2,
                                y2,
                                str(result.names[class_id]),
                                float(detection[-2]),
                            )
                        )

                disparity, points_3d, depth_ms = depth_future.result()
                stereo_ms = rectify_ms + depth_ms
                obstacle_distance = _region_distance(
                    points_3d,
                    disparity,
                    self.obstacle_region,
                    self.min_distance_m,
                    self.max_distance_m,
                    self.distance_mode,
                    self.obstacle_percentile,
                )

                detection_payload = []
                for detection_index, detection in enumerate(cached_detections if detection_active else []):
                    x1, y1, x2, y2, name, confidence = detection
                    color = DETECTION_COLORS[detection_index % len(DETECTION_COLORS)]
                    blue, green, red = color
                    color_hex = f"#{red:02x}{green:02x}{blue:02x}"
                    detection_payload.append(
                        {
                            "name": name,
                            "confidence": round(confidence, 4),
                            "color": color_hex,
                        }
                    )
                    label = f"{name} {confidence:.2f}"
                    cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
                    cv2.putText(
                        annotated,
                        label,
                        (x1, max(20, y1 - 7)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.5,
                        color,
                        2,
                        cv2.LINE_AA,
                    )

                frame_index += 1
                now = time.monotonic()
                instant_fps = 1.0 / max(now - previous_time, 1e-6)
                fps = instant_fps if self._fps == 0.0 else 0.9 * self._fps + 0.1 * instant_fps
                previous_time = now
                depth_view = _disparity_preview(disparity, self.num_disparities)
                region_left, region_top, region_right, region_bottom = self.obstacle_region
                region_x1 = int(depth_view.shape[1] * region_left)
                region_y1 = int(depth_view.shape[0] * region_top)
                region_x2 = int(depth_view.shape[1] * region_right)
                region_y2 = int(depth_view.shape[0] * region_bottom)
                cv2.rectangle(
                    depth_view,
                    (region_x1, region_y1),
                    (region_x2, region_y2),
                    (80, 230, 230),
                    2,
                )
                obstacle_text = (
                    "CENTER CLEARANCE: unavailable"
                    if obstacle_distance is None
                    else f"CENTER CLEARANCE: {obstacle_distance:.2f} m"
                )
                cv2.putText(
                    depth_view,
                    obstacle_text,
                    (region_x1, max(20, region_y1 - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (80, 230, 230),
                    2,
                    cv2.LINE_AA,
                )
                ok_detection, detection_jpeg = cv2.imencode(
                    ".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 82]
                )
                ok_depth, depth_jpeg = cv2.imencode(
                    ".jpg", depth_view, [cv2.IMWRITE_JPEG_QUALITY, 82]
                )
                if not ok_detection or not ok_depth:
                    raise RobotStereoError("Could not encode stereo output frames.")

                with self._condition:
                    if "detection" in self._active_views:
                        self._frames["detection"] = detection_jpeg.tobytes()
                    if "depth" in self._active_views:
                        self._frames["depth"] = depth_jpeg.tobytes()
                    self._sequence += 1
                    self._last_frame_at = time.time()
                    self._detections = detection_payload
                    self._fps = fps
                    self._stereo_ms = stereo_ms
                    self._yolo_ms = last_yolo_ms
                    self._pair_delta_ms = pair_delta_ms
                    self._obstacle_distance_m = (
                        round(obstacle_distance, 3)
                        if obstacle_distance is not None
                        else None
                    )
                    self._state = "connected"
                    self._error = None
                    self._condition.notify_all()
        except Exception as exc:
            if not self._stop_event.is_set():
                self._set_terminal_error(f"Stereo processing stopped: {exc}")
        finally:
            depth_worker.shutdown(wait=True)
            capture.stop()

    def status(self) -> dict[str, object]:
        with self._condition:
            configuration_view = "detection" if "detection" in self._active_views else "depth"
            age = (
                round(time.time() - self._last_frame_at, 3)
                if self._last_frame_at is not None
                else None
            )
            return {
                "configured": self._configuration_error("depth") is None,
                "view_configured": {
                    "detection": self._configuration_error("detection") is None,
                    "depth": self._configuration_error("depth") is None,
                },
                "state": self._state,
                "running": self._thread is not None and self._thread.is_alive(),
                "views": {
                    "detection": "detection" in self._active_views,
                    "depth": "depth" in self._active_views,
                },
                "connected": self._state == "connected" and not self._stop_event.is_set(),
                "error": self._error or self._configuration_error(configuration_view),
                "device": self.device,
                "device_name": self._device_name,
                "object_detection_enabled": self.enable_object_detection,
                "frame_sequence": self._sequence,
                "last_frame_age_seconds": age,
                "detections": list(self._detections) if self._state == "connected" else [],
                "fps": round(self._fps, 1),
                "stereo_ms": round(self._stereo_ms, 1),
                "yolo_ms": round(self._yolo_ms, 1),
                "pair_delta_ms": round(self._pair_delta_ms, 1),
                "baseline_m": self._baseline_m,
                "obstacle_distance_m": self._obstacle_distance_m,
                "obstacle_region": self.obstacle_region,
                "obstacle_percentile": self.obstacle_percentile,
                "disparity_consistency_px": self.disparity_consistency_px,
                "clearance_cell_size_px": CENTER_CLEARANCE_CELL_SIZE_PX,
                "clearance_min_valid_ratio": CENTER_CLEARANCE_MIN_VALID_RATIO,
                "distance_mode": self.distance_mode,
                "classes": list(self.prompts),
                "ports": {"left": self.left_port, "right": self.right_port},
            }

    def mjpeg_stream(self, view: str) -> Iterator[bytes]:
        if view not in self._frames:
            raise RobotStereoError(f"Unknown stereo view: {view}")
        sequence = 0
        while not self._stop_event.is_set():
            with self._condition:
                self._condition.wait_for(
                    lambda: self._sequence > sequence
                    or self._stop_event.is_set()
                    or view not in self._active_views
                    or self._state == "error",
                    timeout=5.0,
                )
                if view not in self._active_views:
                    break
                if self._sequence <= sequence or self._frames[view] is None:
                    if self._state == "error":
                        break
                    continue
                jpeg = self._frames[view]
                sequence = self._sequence
            yield (
                b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                + str(len(jpeg)).encode("ascii")
                + b"\r\n\r\n"
                + jpeg
                + b"\r\n"
            )
