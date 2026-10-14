"""In-process autonomous walking using the shared stereo depth pipeline."""
from __future__ import annotations

import threading
import time
from collections import deque
from statistics import median
from typing import Any

from backend.robot_control import RobotControlError, RobotControlService
from backend.robot_stereo_detection import RobotStereoDetectionService, RobotStereoError


class RobotAutoWalkError(RuntimeError):
    pass


# Number of consecutive fresh stereo frames used for each movement decision.
CLEARANCE_SAMPLE_FRAMES = 8


class RobotAutoWalkService:
    def __init__(self, detector: RobotStereoDetectionService, controller: RobotControlService) -> None:
        self.detector = detector
        self.controller = controller
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._events: deque[dict[str, Any]] = deque(maxlen=30)
        self._event: dict[str, Any] | None = None
        self._error: str | None = None
        self._settings = self.default_settings()

    @staticmethod
    def default_settings() -> dict[str, int | float]:
        return {"forward_steps": 2, "max_right_turns": 10, "clearance_m": 0.5, "forward_speed_m_s": 0.4, "turn_speed_rad_s": 1.0}

    def status(self) -> dict[str, Any]:
        with self._lock:
            running = self._thread is not None and self._thread.is_alive()
            return {
                "configured": bool(self.controller.network_interface), "running": running,
                "state": "running" if running else ("error" if self._error else "stopped"),
                "settings": dict(self._settings), "event": dict(self._event) if self._event else None,
                "events": [dict(event) for event in self._events], "output": [],
                "error": self._error, "exit_code": None,
            }

    def _publish(self, event_type: str, message: str, **details: object) -> None:
        event = {"type": event_type, "message": message, **details}
        with self._lock:
            self._event = event
            self._events.append(dict(event))

    def start(self, forward_steps: int, max_right_turns: int, clearance_m: float, forward_speed_m_s: float, turn_speed_rad_s: float) -> dict[str, Any]:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                raise RobotAutoWalkError("Autonomous walking is already running.")
            if not self.controller.network_interface:
                raise RobotAutoWalkError("UNITREE_NETWORK_INTERFACE is not configured.")
            self._settings = {
                "forward_steps": forward_steps, "max_right_turns": max_right_turns, "clearance_m": clearance_m,
                "forward_speed_m_s": forward_speed_m_s, "turn_speed_rad_s": turn_speed_rad_s,
            }
            self._events.clear()
            self._event = {"type": "starting", "message": "Starting shared depth for autonomous walk…"}
            self._events.append(dict(self._event))
            self._error = None
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run, name="robot-auto-walk", daemon=True)
            self._thread.start()
        return self.status()

    def _wait_for_frame(self, after_sequence: int, timeout: float = 10.0) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        while not self._stop_event.is_set() and time.monotonic() < deadline:
            status = self.detector.status()
            if status.get("state") == "error":
                raise RobotStereoError(str(status.get("error") or "Stereo depth error."))
            if status.get("connected") and int(status.get("frame_sequence", 0)) > after_sequence:
                return status
            time.sleep(0.1)
        if self._stop_event.is_set():
            raise InterruptedError
        raise RobotStereoError("Timed out waiting for a fresh stereo depth frame.")

    def _measure_clearance(
        self,
        after_sequence: int,
    ) -> tuple[float, int]:
        """Return the median clearance from consecutive fresh stereo frames."""
        clearances: list[float] = []
        sequence = after_sequence
        for sample_number in range(1, CLEARANCE_SAMPLE_FRAMES + 1):
            status = self._wait_for_frame(sequence)
            sequence = int(status["frame_sequence"])
            distance = status.get("obstacle_distance_m")
            if not isinstance(distance, (int, float)):
                raise RobotStereoError(
                    "Depth became unreliable while collecting 8 consecutive frames."
                )
            clearances.append(float(distance))
            self._publish(
                "measuring",
                f"Measuring clearance: {sample_number}/{CLEARANCE_SAMPLE_FRAMES} frames.",
                samples_collected=sample_number,
                samples_required=CLEARANCE_SAMPLE_FRAMES,
            )
        return float(median(clearances)), sequence

    def _run(self) -> None:
        completed = turns = last_sequence = 0
        blocked = False
        motion_cleanup_needed = False
        settings = dict(self._settings)
        try:
            self.detector.acquire_depth_consumer("autonomous_walk")
            while completed < int(settings["forward_steps"]) and not self._stop_event.is_set():
                distance, last_sequence = self._measure_clearance(last_sequence)
                if float(distance) < float(settings["clearance_m"]):
                    if turns >= int(settings["max_right_turns"]):
                        self._publish(
                            "blocked",
                            f"Still blocked after {turns} right turn attempts. Robot stopped.",
                            completed_steps=completed,
                            target_steps=settings["forward_steps"],
                            completed_turns=turns,
                            distance_m=round(float(distance), 3),
                        )
                        blocked = True
                        break
                    turns += 1
                    motion_cleanup_needed = True
                    self.controller.execute_velocity(0.0, 0.0, -float(settings["turn_speed_rad_s"]), 1.0)
                    motion_cleanup_needed = False
                    self._publish("turn", f"Right turn {turns} completed.", completed_steps=completed, target_steps=settings["forward_steps"], completed_turns=turns, distance_m=round(float(distance), 3))
                else:
                    motion_cleanup_needed = True
                    self.controller.execute_velocity(float(settings["forward_speed_m_s"]), 0.0, 0.0, 1.0)
                    motion_cleanup_needed = False
                    completed += 1
                    self._publish("step", f"Forward step {completed}/{settings['forward_steps']} completed.", completed_steps=completed, target_steps=settings["forward_steps"], completed_turns=turns, distance_m=round(float(distance), 3))
                last_sequence = int(self.detector.status().get("frame_sequence", last_sequence))
                # Do not keep the UI in "Stop walking" after the final step.
                if completed < int(settings["forward_steps"]):
                    time.sleep(0.6)
            if self._stop_event.is_set():
                self._publish("stopped", "Autonomous walk stopped.")
            elif not blocked:
                self._publish("complete", f"Completed {completed} forward steps.")
        except InterruptedError:
            self._publish("stopped", "Autonomous walk stopped.")
        except Exception as exc:
            with self._lock:
                self._error = str(exc)
            self._publish("error", f"Autonomous walk stopped: {exc}")
        finally:
            # execute_velocity already sends an explicit stop after every
            # successful bounded movement. Retry only when movement raised
            # before confirming that stop, avoiding a duplicate final RPC.
            if motion_cleanup_needed:
                try:
                    self.controller.execute("stop")
                except RobotControlError:
                    pass
            self.detector.release_depth_consumer("autonomous_walk")

    def stop(self) -> dict[str, Any]:
        self._stop_event.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=5.0)
        return self.status()

    def shutdown(self) -> None:
        self.stop()
