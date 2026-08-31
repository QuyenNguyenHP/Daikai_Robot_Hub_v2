"""Manage the XR arm/hand teleoperation subprocess."""

from __future__ import annotations

import os
import signal
import shlex
import subprocess
import threading
import uuid
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
    SCRIPT = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "reference_script",
        "teleop_hand_and_arm.py",
    )

    def __init__(self) -> None:
        self._process: subprocess.Popen[str] | None = None
        self._lock = threading.Lock()
        self._output: deque[str] = deque(maxlen=80)
        self._started_at: str | None = None
        self._input_mode: InputMode | None = None
        self._tracking = False
        self._stopping = False

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
                "tracking": running and self._tracking,
                "stopping": running and self._stopping,
            }

    def _ipc_command(self, command: str, timeout_seconds: float = 1.0) -> None:
        try:
            import zmq
        except ImportError as exc:
            raise TeleoperationError(
                "pyzmq is required for frontend teleoperation controls."
            ) from exc

        context = zmq.Context()
        socket = context.socket(zmq.REQ)
        socket.setsockopt(zmq.LINGER, 0)
        socket.connect("ipc://@xr_teleoperate_data.ipc")
        request_id = str(uuid.uuid4())
        try:
            socket.send_json({"reqid": request_id, "cmd": command})
            if not socket.poll(round(timeout_seconds * 1000)):
                raise TeleoperationError(
                    "Teleoperation control is not ready yet. Try again shortly."
                )
            reply = socket.recv_json()
            if reply.get("status") != "ok" or reply.get("repid") != request_id:
                raise TeleoperationError(
                    f"Teleoperation rejected {command}: {reply.get('msg', 'unknown error')}"
                )
        except TeleoperationError:
            raise
        except Exception as exc:
            raise TeleoperationError(
                f"Could not send teleoperation command {command}: {exc}"
            ) from exc
        finally:
            socket.close()
            context.term()

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
            if not os.path.isfile(self.SCRIPT):
                raise TeleoperationError(
                    f"Project teleoperation script was not found: {self.SCRIPT}"
                )

            command = (
                f"source {self.CONDA_SETUP} && conda activate tv && "
                f"exec python {shlex.quote(self.SCRIPT)} "
                "--frequency=30 "
                f"--input-mode={input_mode} "
                "--display-mode=pass-through "
                "--arm=R1_A5 "
                "--network-interface=eth10 "
                "--no-image-server "
                "--motion "
                "--ipc"
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
            self._tracking = False
            self._stopping = False
            process = self._process

        threading.Thread(
            target=self._read_output,
            args=(process,),
            name="teleoperation-output",
            daemon=True,
        ).start()
        return self.status()

    def begin_tracking(self) -> dict[str, object]:
        with self._lock:
            if not self._is_running():
                raise TeleoperationStateError("Launch teleoperation before tracking.")
            if self._stopping:
                raise TeleoperationStateError("Teleoperation is stopping.")
            if self._tracking:
                raise TeleoperationStateError("Robot tracking is already active.")
        self._ipc_command("CMD_START")
        with self._lock:
            self._tracking = True
        return self.status()

    def _terminate_if_still_running(self, process: subprocess.Popen[str]) -> None:
        try:
            process.wait(timeout=12)
            return
        except subprocess.TimeoutExpired:
            pass
        try:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=5)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)

    def stop(self) -> dict[str, object]:
        with self._lock:
            if not self._is_running() or self._process is None:
                raise TeleoperationStateError("Teleoperation is not running.")
            process = self._process
            self._stopping = True
            self._tracking = False

        try:
            self._ipc_command("CMD_STOP")
        except TeleoperationError:
            with self._lock:
                self._stopping = False
            raise
        threading.Thread(
            target=self._terminate_if_still_running,
            args=(process,),
            name="teleoperation-stop",
            daemon=True,
        ).start()
        return self.status()

    def shutdown(self) -> None:
        if self._is_running():
            try:
                self.stop()
            except TeleoperationError:
                process = self._process
                if process is not None and process.poll() is None:
                    try:
                        os.killpg(process.pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
