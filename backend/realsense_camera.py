"""Optional USB RealSense D415 capture for the shared vision/depth worker."""
import os
import logging


LOGGER = logging.getLogger(__name__)


class D415Capture:
    def __init__(self):
        import pyrealsense2 as rs
        self.rs = rs
        self.pipeline = rs.pipeline()
        self.started = False
        self.depth_enabled = False
        self.color_width = int(os.getenv("R1_D415_COLOR_WIDTH", "1280"))
        self.color_height = int(os.getenv("R1_D415_COLOR_HEIGHT", "720"))
        self.align = rs.align(rs.stream.color)
        self.cloud = rs.pointcloud()

    def start(self, *, need_depth=False):
        rs = self.rs
        serial = os.getenv("R1_D415_SERIAL", "").strip()
        devices = rs.context().query_devices()
        device = next((d for d in devices
                       if "D415" in d.get_info(rs.camera_info.name)
                       and (not serial or d.get_info(rs.camera_info.serial_number) == serial)), None)
        if device is None:
            raise RuntimeError("No USB RealSense D415 found on the backend host.")
        # USB negotiation/SDK builds may expose a different set of profiles.
        # Test the complete color/depth combination, then let the SDK choose
        # resolution and FPS as a final fallback. Never enable depth for Console.
        candidates = list(dict.fromkeys((
            (self.color_width, self.color_height, 30),
            (640, 480, 30),
            (640, 480, 15),
            (0, 0, 0),
        )))
        failures = []
        wrapper = rs.pipeline_wrapper(self.pipeline)
        for width, height, fps in candidates:
            config = rs.config()
            config.disable_all_streams()
            config.enable_device(device.get_info(rs.camera_info.serial_number))
            if need_depth:
                config.enable_stream(rs.stream.depth, 640 if width else 0,
                                     480 if height else 0, rs.format.z16, fps)
            config.enable_stream(rs.stream.color, width, height, rs.format.bgr8, fps)
            label = f"{width}x{height}@{fps}" if width else "SDK automatic"
            try:
                if not config.can_resolve(wrapper):
                    failures.append(f"{label}: unsupported stream combination")
                    continue
                self.pipeline.start(config)
            except RuntimeError as exc:
                failures.append(f"{label}: {exc}")
                continue
            self.started = True
            self.depth_enabled = need_depth
            LOGGER.info("D415 started: color=%s, depth=%s", label, need_depth)
            return
        raise RuntimeError(
            "D415 could not open a compatible color" + ("/depth" if need_depth else "-only")
            + " stream. Close other camera apps and check the USB connection. Attempts: "
            + "; ".join(failures)
        )

    def read(self, *, need_depth=True):
        import numpy as np
        if need_depth != self.depth_enabled:
            self.stop()
            self.start(need_depth=need_depth)
        frames = self.pipeline.wait_for_frames(2000)
        # Always copy native RGB BEFORE any alignment. Alignment output must
        # never become the Console preview (holes/occlusions belong to depth).
        color = frames.get_color_frame()
        if not color:
            raise RuntimeError("D415 did not return a color frame.")
        image = np.asanyarray(color.get_data()).copy()
        if not need_depth:
            return image, None, None
        aligned = self.align.process(frames)
        depth = aligned.get_depth_frame()
        if not depth:
            raise RuntimeError("D415 did not return a synchronized depth frame.")
        cloud = self.cloud.calculate(depth)
        points = np.asanyarray(cloud.get_vertices()).view(np.float32).reshape(
            depth.get_height(), depth.get_width(), 3).copy()
        # Shared depth helpers use this mask to reject missing depth pixels.
        valid = (points[:, :, 2] > 0).astype(np.float32)
        return image, valid, points

    def stop(self):
        if self.started:
            self.pipeline.stop()
            self.started = False
