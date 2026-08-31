"""Bounded locomotion control for the Unitree R1."""

from __future__ import annotations

import json
import math
import os
import threading
import time

from backend.unitree_dds import UNITREE_DDS_INIT_LOCK


COMMAND_DURATION = 1.0
LINEAR_SPEED = 0.5
LATERAL_SPEED = 0.4
TURN_SPEED = math.radians(60.0)
LOCOMOTION_FSM_ID = 811
LOCOMOTION_FSM_IDS = frozenset({811, 816})
FSM_NAMES = {
    0: "ZERO TORQUE",
    1: "DAMPING",
    4: "STANCE",
    701: "LIE TO STAND",
    702: "STAND TO LIE",
    811: "LOCOMOTION",
    816: "LOCOMOTION",
}

VELOCITY_COMMANDS = {
    "forward": (LINEAR_SPEED, 0.0, 0.0),
    "backward": (-LINEAR_SPEED, 0.0, 0.0),
    "left": (0.0, LATERAL_SPEED, 0.0),
    "right": (0.0, -LATERAL_SPEED, 0.0),
    "turn_left": (0.0, 0.0, TURN_SPEED),
    "turn_right": (0.0, 0.0, -TURN_SPEED),
}


class RobotControlError(RuntimeError):
    """Raised when the robot rejects or cannot execute a control command."""


class RobotControlBusyError(RobotControlError):
    """Raised when another control command is still running."""


class RobotControlStateError(RobotControlError):
    """Raised when a command is invalid for the current locomotion state."""


class RobotControlService:
    """Own one R1 LocoClient and execute short, serialized commands."""

    def __init__(self, network_interface: str | None = None) -> None:
        self.network_interface = (
            network_interface or os.getenv("UNITREE_NETWORK_INTERFACE", "")
        ).strip()
        self._lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._client = None
        self._locomotion_started = False
        self._last_fsm_id: int | None = None
        try:
            preferred_fsm_id = int(
                os.getenv("UNITREE_LOCOMOTION_FSM_ID", str(LOCOMOTION_FSM_ID))
            )
        except ValueError:
            preferred_fsm_id = LOCOMOTION_FSM_ID
        self._preferred_locomotion_fsm_id = (
            preferred_fsm_id
            if preferred_fsm_id in LOCOMOTION_FSM_IDS
            else LOCOMOTION_FSM_ID
        )
        self._last_action: str | None = None
        self._last_code: int | None = None
        self._error: str | None = None
        self._polishing_stop = threading.Event()
        self._polishing_thread: threading.Thread | None = None
        self._polishing_arm: str | None = None
        self._polishing_speed_deg_s: float | None = None
        self._polishing_hold_seconds: float | None = None

    def status(self) -> dict[str, object]:
        with self._state_lock:
            payload = {
                "process_id": os.getpid(),
                "configured": bool(self.network_interface),
                "initialized": self._client is not None,
                "busy": self._lock.locked(),
                "locomotion_started": self._locomotion_started,
                "last_fsm_id": self._last_fsm_id,
                "accepted_locomotion_fsm_ids": sorted(LOCOMOTION_FSM_IDS),
                "preferred_locomotion_fsm_id": self._preferred_locomotion_fsm_id,
                "last_action": self._last_action,
                "last_code": self._last_code,
                "error": self._error,
                "command_duration_seconds": COMMAND_DURATION,
                "linear_speed_mps": LINEAR_SPEED,
                "lateral_speed_mps": LATERAL_SPEED,
                "turn_speed_radps": TURN_SPEED,
                "polishing_active": bool(
                    self._polishing_thread and self._polishing_thread.is_alive()
                ),
                "polishing_arm": self._polishing_arm,
                "polishing_speed_deg_s": self._polishing_speed_deg_s,
                "polishing_hold_seconds": self._polishing_hold_seconds,
            }
        return payload

    def _client_instance(self):
        if self._client is not None:
            return self._client
        if not self.network_interface:
            raise RobotControlError("UNITREE_NETWORK_INTERFACE is not configured.")

        try:
            from unitree_sdk2py.core.channel import ChannelFactoryInitialize
            from unitree_sdk2py.r1.loco.r1_loco_client import LocoClient
        except ImportError as exc:
            raise RobotControlError(
                f"Unitree SDK could not be imported: {exc}"
            ) from exc

        try:
            with UNITREE_DDS_INIT_LOCK:
                ChannelFactoryInitialize(0, self.network_interface)
                client = LocoClient()
                client.SetTimeout(3.0)
                client.Init()
        except Exception as exc:
            raise RobotControlError(
                f"Could not initialize the Unitree locomotion client: {exc}"
            ) from exc

        self._client = client
        return client

    @staticmethod
    def _fsm_id(client) -> int:
        try:
            from unitree_sdk2py.r1.loco.r1_loco_api import (
                ROBOT_API_ID_LOCO_GET_FSM_ID,
            )
        except ImportError as exc:
            raise RobotControlError(
                f"Unitree FSM API could not be imported: {exc}"
            ) from exc

        code, data = client._Call(ROBOT_API_ID_LOCO_GET_FSM_ID, "{}")
        if code != 0:
            raise RobotControlError(f"FSM mode query failed with code {code}.")
        try:
            return int(json.loads(data)["data"])
        except (TypeError, ValueError, KeyError, json.JSONDecodeError) as exc:
            raise RobotControlError(
                "The robot FSM mode response could not be decoded."
            ) from exc

    def _require_locomotion(self, client) -> None:
        # Query the robot instead of relying only on local state. The backend
        # may have started while the robot was already in locomotion mode.
        fsm_id = self._fsm_id(client)
        self._set_fsm_state(fsm_id)
        if fsm_id not in LOCOMOTION_FSM_IDS:
            raise RobotControlStateError(
                "Enable locomotion before sending robot control commands; "
                f"accepted FSM IDs are {sorted(LOCOMOTION_FSM_IDS)}, got {fsm_id}."
            )

    def _set_fsm_state(self, fsm_id: int) -> None:
        with self._state_lock:
            self._last_fsm_id = fsm_id
            self._locomotion_started = fsm_id in LOCOMOTION_FSM_IDS
            if self._locomotion_started:
                self._preferred_locomotion_fsm_id = fsm_id

    def _mode_payload(
        self,
        fsm_id: int | None,
        *,
        control_busy: bool,
        stale: bool,
    ) -> dict[str, object]:
        if fsm_id is None:
            fsm_name = "UNKNOWN"
            display = "Mode query pending"
        else:
            fsm_name = FSM_NAMES.get(fsm_id, "UNKNOWN/UNDOCUMENTED")
            display = f"{fsm_name} (ID {fsm_id})"
        return {
            "process_id": os.getpid(),
            "configured": bool(self.network_interface),
            "fsm_id": fsm_id,
            "fsm_name": fsm_name,
            "display": display,
            "control_busy": control_busy,
            "stale": stale,
        }

    @staticmethod
    def _require_success(code: int, action: str) -> None:
        if code != 0:
            raise RobotControlError(
                f"Robot rejected {action.replace('_', ' ')} with code {code}."
            )

    def _set_result(
        self,
        action: str,
        code: int | None = None,
        error: str | None = None,
    ) -> None:
        with self._state_lock:
            self._last_action = action
            self._last_code = code
            self._error = error

    def _polishing_worker(
        self, client, arm: str, speed_deg_s: float, hold_seconds: float
    ) -> None:
        try:
            from backend.robot_polishing import run_polishing_action

            code = run_polishing_action(
                client,
                arm=arm,
                speed_deg_s=speed_deg_s,
                hold_duration=hold_seconds,
                stop_event=self._polishing_stop,
            )
            if code != 0:
                self._set_result(
                    "crankshaft_polishing", error=f"Polishing stopped with code {code}."
                )
        except Exception as exc:
            self._set_result(
                "crankshaft_polishing", error=f"Crankshaft polishing failed: {exc}"
            )
        finally:
            with self._state_lock:
                self._polishing_arm = None
                self._polishing_speed_deg_s = None
                self._polishing_hold_seconds = None

    def _stop_polishing(self) -> None:
        thread = self._polishing_thread
        if thread is None or not thread.is_alive():
            self._polishing_thread = None
            return
        self._polishing_stop.set()
        thread.join(timeout=5.0)
        if thread.is_alive():
            raise RobotControlBusyError("Polishing is still releasing arm control.")
        self._polishing_thread = None

    def execute(
        self,
        action: str,
        *,
        arm: str = "right",
        speed_deg_s: float = 120.0,
        hold_seconds: float = 0.05,
    ) -> dict[str, object]:
        if not self._lock.acquire(blocking=False):
            raise RobotControlBusyError("Another robot control command is running.")

        details: dict[str, object] = {}
        try:
            client = self._client_instance()

            polishing_active = bool(
                self._polishing_thread and self._polishing_thread.is_alive()
            )
            if polishing_active and action != "crankshaft_stop":
                raise RobotControlBusyError(
                    "Stop crankshaft polishing before sending another command."
                )

            if action == "stance":
                with self._state_lock:
                    locomotion_started = self._locomotion_started
                if locomotion_started:
                    # Some R1 firmware returns 127 for this best-effort stop
                    # while still accepting the following FSM transition.
                    client.SetVelocity(0.0, 0.0, 0.0, COMMAND_DURATION)
                code = client.SetFsmId(4)
                self._require_success(code, "enter stance mode")
                self._set_fsm_state(4)

            elif action == "zero_torque":
                code = client.SetFsmId(0)
                self._require_success(code, "enter zero torque mode")
                self._set_fsm_state(0)

            elif action == "enable":
                code = client.SetFsmId(4)
                self._require_success(code, "enter stance mode")
                time.sleep(0.5)
                with self._state_lock:
                    locomotion_fsm_id = self._preferred_locomotion_fsm_id
                code = client.SetFsmId(locomotion_fsm_id)
                self._require_success(code, "enable locomotion")
                self._set_fsm_state(locomotion_fsm_id)

            elif action == "teleoperation_stop":
                # XR arm control enters FSM 816. Restore the R1's normal
                # locomotion state immediately when the web UI stops teleop.
                client.SetVelocity(0.0, 0.0, 0.0, COMMAND_DURATION)
                code = client.SetFsmId(LOCOMOTION_FSM_ID)
                self._require_success(code, "restore locomotion after teleoperation")
                self._set_fsm_state(LOCOMOTION_FSM_ID)

            elif action == "disable":
                code = client.SetVelocity(0.0, 0.0, 0.0, COMMAND_DURATION)
                self._require_success(code, "disable control")
                code = client.SetFsmId(4)
                self._require_success(code, "return to stance mode")
                self._set_fsm_state(4)

            elif action == "stop":
                self._require_locomotion(client)
                code = client.SetVelocity(0.0, 0.0, 0.0, COMMAND_DURATION)
                self._require_success(code, action)

            elif action == "lie_to_stand":
                fsm_id = self._fsm_id(client)
                self._set_fsm_state(fsm_id)
                if fsm_id not in {0, 1}:
                    raise RobotControlStateError(
                        "Lie to stand is only available in zero torque or damping "
                        f"mode (FSM 0 or 1); current FSM is {fsm_id}."
                    )
                client.SetVelocity(0.0, 0.0, 0.0, COMMAND_DURATION)
                code = client.SetFsmId(4)
                self._require_success(code, "enter stance before lie to stand")
                self._set_fsm_state(4)
                time.sleep(3.0)
                code = client.SetFsmId(701)
                self._require_success(code, action)
                self._set_fsm_state(701)

            elif action == "stand_to_lie":
                self._require_locomotion(client)
                client.SetVelocity(0.0, 0.0, 0.0, COMMAND_DURATION)
                code = client.SetFsmId(702)
                self._require_success(code, action)
                self._set_fsm_state(702)

            elif action == "crankshaft_start":
                self._require_locomotion(client)
                if self._last_fsm_id != LOCOMOTION_FSM_ID:
                    raise RobotControlStateError(
                        "Crankshaft polishing requires locomotion FSM 811."
                    )
                self._polishing_stop.clear()
                with self._state_lock:
                    self._polishing_arm = arm
                    self._polishing_speed_deg_s = speed_deg_s
                    self._polishing_hold_seconds = hold_seconds
                self._polishing_thread = threading.Thread(
                    target=self._polishing_worker,
                    args=(client, arm, speed_deg_s, hold_seconds),
                    name="robot-crankshaft-polishing",
                    daemon=True,
                )
                self._polishing_thread.start()
                details = {
                    "arm": arm,
                    "speed_deg_s": speed_deg_s,
                    "hold_seconds": hold_seconds,
                }

            elif action == "crankshaft_stop":
                self._stop_polishing()
                code = 0

            elif action in VELOCITY_COMMANDS:
                self._require_locomotion(client)
                vx, vy, omega = VELOCITY_COMMANDS[action]
                code = client.SetVelocity(vx, vy, omega, COMMAND_DURATION)
                self._require_success(code, action)

            else:
                raise RobotControlError(f"Unsupported robot action: {action}")

            self._set_result(action, code=code)
        except RobotControlError as exc:
            self._set_result(action, error=str(exc))
            raise
        except Exception as exc:
            message = f"Robot control failed: {exc}"
            self._set_result(action, error=message)
            raise RobotControlError(message) from exc
        finally:
            self._lock.release()
        return {"ok": True, "action": action, **details, **self.status()}

    def mode(self) -> dict[str, object]:
        """Query the robot's registered FSM mode through locomotion API 7001."""
        if not self._lock.acquire(blocking=False):
            # Mode is polled by the UI while long-running robot commands are in
            # progress. Return the most recent observation instead of turning
            # a harmless status poll into HTTP 409.
            with self._state_lock:
                fsm_id = self._last_fsm_id
            return self._mode_payload(fsm_id, control_busy=True, stale=True)

        try:
            client = self._client_instance()
            fsm_id = self._fsm_id(client)
            self._set_fsm_state(fsm_id)
            return self._mode_payload(fsm_id, control_busy=False, stale=False)
        except RobotControlError:
            raise
        except Exception as exc:
            raise RobotControlError(f"FSM mode query failed: {exc}") from exc
        finally:
            self._lock.release()

    def stop(self) -> None:
        """Send a final stop during shutdown when the client was initialized."""
        client = self._client
        if client is None:
            return
        self._polishing_stop.set()
        thread = self._polishing_thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=5.0)
        with self._lock:
            try:
                client.SetVelocity(0.0, 0.0, 0.0, COMMAND_DURATION)
            except Exception:
                pass
