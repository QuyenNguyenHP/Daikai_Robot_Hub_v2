"""Manage the GStreamer UDP/RTP video relay used by the Console page."""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import threading
from collections import deque


class VideoStreamingError(RuntimeError):
    """Raised when the GStreamer relay cannot be managed."""


class VideoStreamingStateError(VideoStreamingError):
    """Raised when a relay request conflicts with its current state."""


class VideoStreamingService:
    """Own one UDP video relay subprocess."""

    def __init__(self) -> None:
        self._process: subprocess.Popen[str] | None = None
        self._destination_ip: str | None = None
        self._output: deque[str] = deque(maxlen=40)
        self._lock = threading.Lock()

    def _is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def status(self) -> dict[str, object]:
        with self._lock:
            running = self._is_running()
            return {
                "running": running,
                "pid": self._process.pid if running and self._process else None,
                "destination_ip": self._destination_ip,
                "source_port": 5001,
                "destination_port": 5000,
                "exit_code": (
                    None if self._process is None or running else self._process.returncode
                ),
                "output": list(self._output),
            }

    def _read_output(self, process: subprocess.Popen[str]) -> None:
        if process.stdout is None:
            return
        for line in process.stdout:
            with self._lock:
                self._output.append(line.rstrip())

    def start(self, destination_ip: str) -> dict[str, object]:
        with self._lock:
            if self._is_running():
                raise VideoStreamingStateError("Video streaming is already running.")
            executable = shutil.which("gst-launch-1.0")
            if executable is None:
                raise VideoStreamingError(
                    "gst-launch-1.0 was not found. Install GStreamer on the backend host."
                )
            command = [
                executable,
                "-v",
                "udpsrc",
                "address=0.0.0.0",
                "port=5001",
                "caps=application/x-rtp,media=video,encoding-name=H264,clock-rate=90000",
                "!",
                "queue",
                "!",
                "udpsink",
                f"host={destination_ip}",
                "port=5000",
                "sync=false",
                "async=false",
            ]
            self._output.clear()
            try:
                self._process = subprocess.Popen(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    start_new_session=True,
                )
            except OSError as exc:
                raise VideoStreamingError(
                    f"Could not start the GStreamer relay: {exc}"
                ) from exc
            self._destination_ip = destination_ip
            process = self._process

        threading.Thread(
            target=self._read_output,
            args=(process,),
            name="video-stream-output",
            daemon=True,
        ).start()
        return self.status()

    def stop(self) -> dict[str, object]:
        with self._lock:
            if not self._is_running() or self._process is None:
                raise VideoStreamingStateError("Video streaming is not running.")
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
