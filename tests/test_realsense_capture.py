import unittest
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np

from backend.realsense_camera import D415Capture


class D415CaptureTests(unittest.TestCase):
    def capture(self, need_depth=False):
        capture = D415Capture.__new__(D415Capture)
        raw = np.full((2, 3, 3), 150, np.uint8)
        color = SimpleNamespace(get_data=lambda: raw)
        frames = SimpleNamespace(get_color_frame=lambda: color)
        capture.depth_enabled = need_depth
        capture.pipeline = Mock()
        capture.pipeline.wait_for_frames.return_value = frames
        capture.align = Mock()
        capture.cloud = Mock()
        return capture, raw

    def test_console_uses_native_rgb_without_depth_processing(self):
        capture, raw = self.capture()
        image, valid, points = capture.read(need_depth=False)
        np.testing.assert_array_equal(image, raw)
        image[0, 0] = 0
        self.assertTrue(np.all(raw == 150))
        self.assertIsNone(valid)
        self.assertIsNone(points)
        capture.align.process.assert_not_called()
        capture.cloud.calculate.assert_not_called()

    def test_depth_alignment_cannot_replace_rgb_with_black_holes(self):
        capture, raw = self.capture(need_depth=True)
        vertices = np.zeros((2, 3, 3), np.float32)
        vertices[:, :, 2] = 2.0
        depth = SimpleNamespace(get_height=lambda: 2, get_width=lambda: 3)
        capture.align.process.return_value = SimpleNamespace(
            get_depth_frame=lambda: depth,
            get_color_frame=lambda: SimpleNamespace(get_data=lambda: np.zeros_like(raw)),
        )
        capture.cloud.calculate.return_value = SimpleNamespace(get_vertices=lambda: vertices)
        image, valid, points = capture.read(need_depth=True)
        np.testing.assert_array_equal(image, raw)
        np.testing.assert_array_equal(valid, np.ones((2, 3)))
        np.testing.assert_array_equal(points[:, :, 2], np.full((2, 3), 2.0))

    def test_console_camera_configuration_does_not_enable_depth_stream(self):
        for need_depth in (False, True):
            with self.subTest(need_depth=need_depth):
                capture, _ = self.capture()
                device = Mock()
                device.get_info.side_effect = lambda field: "Intel RealSense D415" if field == "name" else "serial"
                config = Mock()
                capture.rs = SimpleNamespace(
                    context=lambda: SimpleNamespace(query_devices=lambda: [device]),
                    config=lambda: config,
                    pipeline_wrapper=lambda pipeline: pipeline,
                    camera_info=SimpleNamespace(name="name", serial_number="serial"),
                    stream=SimpleNamespace(depth="depth", color="color"),
                    format=SimpleNamespace(z16="z16", bgr8="bgr8"),
                )
                capture.color_width, capture.color_height = 1280, 720
                capture.start(need_depth=need_depth)
                streams = [call.args[0] for call in config.enable_stream.call_args_list]
                self.assertEqual(streams, ["depth", "color"] if need_depth else ["color"])
                self.assertEqual(capture.depth_enabled, need_depth)

    def test_stopping_walk_returns_capture_to_color_only(self):
        capture, raw = self.capture(need_depth=True)
        capture.stop = Mock()

        def start(*, need_depth=False):
            capture.depth_enabled = need_depth

        capture.start = Mock(side_effect=start)
        image, valid, points = capture.read(need_depth=False)
        capture.stop.assert_called_once()
        capture.start.assert_called_once_with(need_depth=False)
        np.testing.assert_array_equal(image, raw)
        self.assertIsNone(points)
        capture.align.process.assert_not_called()

    def startup_capture(self, resolutions):
        capture, _ = self.capture()
        capture.started = False
        capture.color_width, capture.color_height = 1280, 720
        configs = [Mock() for _ in resolutions]
        for config, supported in zip(configs, resolutions):
            config.can_resolve.return_value = supported
        device = SimpleNamespace(get_info=lambda field: "Intel RealSense D415" if field == "name" else "serial")
        capture.rs = SimpleNamespace(
            context=lambda: SimpleNamespace(query_devices=lambda: [device]),
            config=Mock(side_effect=configs),
            pipeline_wrapper=lambda pipeline: pipeline,
            camera_info=SimpleNamespace(name="name", serial_number="serial"),
            stream=SimpleNamespace(depth="depth", color="color"),
            format=SimpleNamespace(z16="z16", bgr8="bgr8"),
        )
        return capture, configs

    def test_unsupported_hd_falls_back_to_vga_without_enabling_depth(self):
        capture, configs = self.startup_capture([False, True])
        capture.start(need_depth=False)
        capture.pipeline.start.assert_called_once_with(configs[1])
        configs[1].enable_stream.assert_called_once_with("color", 640, 480, "bgr8", 30)
        for config in configs:
            config.disable_all_streams.assert_called_once()
            self.assertEqual([c.args[0] for c in config.enable_stream.call_args_list], ["color"])

    def test_sdk_can_choose_resolution_and_fps_for_depth_fallback(self):
        capture, configs = self.startup_capture([False, False, False, True])
        capture.start(need_depth=True)
        capture.pipeline.start.assert_called_once_with(configs[3])
        self.assertEqual([c.args for c in configs[3].enable_stream.call_args_list],
                         [("depth", 0, 0, "z16", 0), ("color", 0, 0, "bgr8", 0)])
        self.assertTrue(capture.depth_enabled)

    def test_reports_all_failed_configurations(self):
        capture, configs = self.startup_capture([False, False, False, False])
        with self.assertRaisesRegex(RuntimeError, "compatible color-only"):
            capture.start(need_depth=False)
        capture.pipeline.start.assert_not_called()
        self.assertFalse(capture.started)

    def test_start_resolution_failure_tries_next_configuration(self):
        capture, configs = self.startup_capture([True, True])
        capture.pipeline.start.side_effect = [RuntimeError("Couldn't resolve requests"), Mock()]
        capture.start(need_depth=False)
        self.assertEqual(capture.pipeline.start.call_count, 2)
        self.assertTrue(capture.started)
