"""Manage the XR arm/hand teleoperation subprocess."""

from __future__ import annotations

import os
import signal
import subprocess
import threading
from collections import deque
from datetime import datetime, timezone
from typing import Literal


InputMode = Literal["hand", "controller"]


class TeleoperationError(RuntimeError):
    """Raised when the teleoperation process cannot be managed."""


class TeleoperationStateError(TeleoperationError):
    """Raised when a start/stop request conflicts with the current state."""


class RobotTeleoperationService:
    """Start one configured teleoperation process and expose its status."""

    CONDA_SETUP = "/home/unitree/miniconda3/etc/profile.d/conda.sh"
    WORKING_DIRECTORY = "/home/unitree/xr_teleoperate/teleop"

    def __init__(self) -> None:
        self._process: subprocess.Popen[str] | None = None
        self._lock = threading.Lock()
        self._output: deque[str] = deque(maxlen=80)
        self._started_at: str | None = None
        self._input_mode: InputMode | None = None

    def _is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def status(self) -> dict[str, object]:
        with self._lock:
            running = self._is_running()
            return {
                "running": running,
                "pid": self._process.pid if running and self._process else None,
                "input_mode": self._input_mode,
                "started_at": self._started_at,
                "exit_code": (
                    None if self._process is None or running else self._process.returncode
                ),
                "output": list(self._output),
                "motion": True,
                "no_image_server": True,
            }

    def _read_output(self, process: subprocess.Popen[str]) -> None:
        if process.stdout is None:
            return
        for line in process.stdout:
            with self._lock:
                self._output.append(line.rstrip())

    def start(self, input_mode: InputMode) -> dict[str, object]:
        if input_mode not in {"hand", "controller"}:
            raise TeleoperationError("Input mode must be 'hand' or 'controller'.")

        with self._lock:
            if self._is_running():
                raise TeleoperationStateError("Teleoperation is already running.")
            if not os.path.isfile(self.CONDA_SETUP):
                raise TeleoperationError(
                    f"Conda setup script was not found: {self.CONDA_SETUP}"
                )
            if not os.path.isdir(self.WORKING_DIRECTORY):
                raise TeleoperationError(
                    f"Teleoperation directory was not found: {self.WORKING_DIRECTORY}"
                )

            command = (
                f"source {self.CONDA_SETUP} && conda activate tv && "
                "exec python teleop_hand_and_arm.py "
                "--frequency=30 "
                f"--input-mode={input_mode} "
                "--display-mode=pass-through "
                "--arm=R1_A5 "
                "--network-interface=eth10 "
                "--no-image-server "
                "--motion"
            )
            self._output.clear()
            try:
                self._process = subprocess.Popen(
                    ["/bin/bash", "-lc", command],
                    cwd=self.WORKING_DIRECTORY,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    start_new_session=True,
                )
            except OSError as exc:
                raise TeleoperationError(
                    f"Could not start teleoperation: {exc}"
                ) from exc
            self._input_mode = input_mode
            self._started_at = datetime.now(timezone.utc).isoformat()
            process = self._process

        threading.Thread(
            target=self._read_output,
            args=(process,),
            name="teleoperation-output",
            daemon=True,
        ).start()
        return self.status()

    def stop(self) -> dict[str, object]:
        with self._lock:
            if not self._is_running() or self._process is None:
                raise TeleoperationStateError("Teleoperation is not running.")
            process = self._process

        try:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=8)
        except ProcessLookupError:
            pass
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=3)
        return self.status()

    def shutdown(self) -> None:
        if self._is_running():
            try:
                self.stop()
            except TeleoperationError:
                pass
