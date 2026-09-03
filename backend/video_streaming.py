"""Expose the robot's RTP/H.264 feed as browser-compatible MJPEG."""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import threading
from collections import deque
from collections.abc import Iterator


class VideoStreamingError(RuntimeError):
    """Raised when the GStreamer viewer cannot be managed."""


class VideoStreamingStateError(VideoStreamingError):
    """Raised when a viewer request conflicts with its current state."""


class VideoStreamingService:
    """Own one RTP-to-MJPEG subprocess for the web console."""

    def __init__(self) -> None:
        self._process: subprocess.Popen[bytes] | None = None
        self._output: deque[str] = deque(maxlen=40)
        self._lock = threading.Lock()
        self._stream_connected = False

    def _is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def status(self) -> dict[str, object]:
        with self._lock:
            running = self._is_running()
            return {
                "running": running,
                "pid": self._process.pid if running and self._process else None,
                "source_port": 5003,
                "viewer_connected": self._stream_connected if running else False,
                "exit_code": None if self._process is None or running else self._process.returncode,
                "output": list(self._output),
            }

    def _read_output(self, process: subprocess.Popen[bytes]) -> None:
        if process.stderr is None:
            return
        for line in process.stderr:
            with self._lock:
                self._output.append(line.decode(errors="replace").rstrip())

    def start(self) -> dict[str, object]:
        with self._lock:
            if self._is_running():
                raise VideoStreamingStateError("Video viewer is already running.")
            executable = shutil.which("gst-launch-1.0")
            if executable is None:
                raise VideoStreamingError(
                    "gst-launch-1.0 was not found. Install GStreamer on the backend host."
                )
            command = [
                executable, "-q", "udpsrc", "address=0.0.0.0", "port=5003",
                "caps=application/x-rtp,media=video,encoding-name=H264,clock-rate=90000",
                "!", "rtph264depay", "!", "h264parse", "!", "avdec_h264", "!",
                "videoconvert", "!", "jpegenc", "quality=80", "!", "multipartmux",
                "boundary=frame", "!", "fdsink", "fd=1", "sync=false",
            ]
            self._output.clear()
            try:
                self._process = subprocess.Popen(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    start_new_session=True,
                )
            except OSError as exc:
                raise VideoStreamingError(f"Could not start the GStreamer viewer: {exc}") from exc
            self._stream_connected = False
            process = self._process

        threading.Thread(
            target=self._read_output, args=(process,), name="video-viewer-output", daemon=True
        ).start()
        return self.status()

    def stream(self) -> Iterator[bytes]:
        with self._lock:
            if not self._is_running() or self._process is None:
                raise VideoStreamingStateError("Start the video viewer first.")
            if self._stream_connected:
                raise VideoStreamingStateError("The video viewer is already open.")
            process = self._process
            self._stream_connected = True

        try:
            if process.stdout is None:
                raise VideoStreamingError("The video viewer has no media output.")
            while process.poll() is None:
                chunk = process.stdout.read1(64 * 1024)
                if not chunk:
                    break
                yield chunk
        finally:
            with self._lock:
                self._stream_connected = False

    def stop(self) -> dict[str, object]:
        with self._lock:
            if not self._is_running() or self._process is None:
                raise VideoStreamingStateError("Video viewer is not running.")
            process = self._process
        try:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=5)
        except ProcessLookupError:
            pass
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=2)
        return self.status()

    def shutdown(self) -> None:
        if self._is_running():
            try:
                self.stop()
            except VideoStreamingError:
                pass
