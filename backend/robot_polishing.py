"""Crankshaft polishing controller for the Unitree R1 web backend."""

from __future__ import annotations

import json
import math
import threading
import time
from dataclasses import dataclass
from typing import Literal

from unitree_sdk2py.core.channel import ChannelPublisher, ChannelSubscriber
from unitree_sdk2py.idl.default import unitree_hg_msg_dds__LowCmd_
from unitree_sdk2py.idl.unitree_hg.msg.dds_ import LowCmd_, LowState_
from unitree_sdk2py.r1.loco.r1_loco_api import ROBOT_API_ID_LOCO_GET_FSM_ID
from unitree_sdk2py.utils.crc import CRC


LOCOMOTION_FSM_ID = 811
CONTROL_PERIOD = 0.01
STATE_TIMEOUT = 1.0
WEIGHT_RAMP_DURATION = 1.0
MINIMUM_JERK_PEAK_SLOPE = 1.875
ArmSelection = Literal["left", "right", "both"]


@dataclass(frozen=True)
class Joint:
    name: str
    index: int
    kp: float
    kd: float


LEFT_ARM = (
    Joint("Left shoulder pitch", 15, 50.0, 2.0),
    Joint("Left shoulder roll", 16, 50.0, 2.0),
    Joint("Left shoulder yaw", 17, 40.0, 2.0),
    Joint("Left elbow", 18, 40.0, 2.0),
    Joint("Left wrist roll", 19, 30.0, 2.0),
)
RIGHT_ARM = (
    Joint("Right shoulder pitch", 22, 50.0, 2.0),
    Joint("Right shoulder roll", 23, 50.0, 2.0),
    Joint("Right shoulder yaw", 24, 40.0, 2.0),
    Joint("Right elbow", 25, 40.0, 2.0),
    Joint("Right wrist roll", 26, 30.0, 2.0),
)
HELD_JOINTS = (
    Joint("Waist yaw", 13, 50.0, 3.0),
    Joint("Head pitch", 29, 15.0, 1.0),
    Joint("Head yaw", 30, 15.0, 1.0),
)

POSE_1_VALUES = (-0.092380, 0.015358, 0.145309, -0.068757, 0.064654)
POSE_2_VALUES = (0.375244, POSE_1_VALUES[1], POSE_1_VALUES[2], -0.464781, POSE_1_VALUES[4])
POSE_3_VALUES = (-0.618961, POSE_1_VALUES[1], POSE_1_VALUES[2], 0.633055, POSE_1_VALUES[4])


def _mirrored_values(values: tuple[float, ...]) -> tuple[float, ...]:
    # R1 pitch and elbow use matching bilateral signs. Roll and yaw axes mirror.
    return (values[0], -values[1], -values[2], values[3], -values[4])


def _action_poses(arm: ArmSelection) -> tuple[dict[int, float], ...]:
    poses: list[dict[int, float]] = []
    for values in (POSE_1_VALUES, POSE_2_VALUES, POSE_3_VALUES):
        pose: dict[int, float] = {}
        if arm in {"right", "both"}:
            pose.update({joint.index: value for joint, value in zip(RIGHT_ARM, values)})
        if arm in {"left", "both"}:
            pose.update(
                {
                    joint.index: value
                    for joint, value in zip(LEFT_ARM, _mirrored_values(values))
                }
            )
        poses.append(pose)
    return tuple(poses)


def _fsm_id(client) -> tuple[int, int | None]:
    code, data = client._Call(ROBOT_API_ID_LOCO_GET_FSM_ID, "{}")
    if code != 0:
        return code, None
    try:
        return code, int(json.loads(data)["data"])
    except (TypeError, ValueError, KeyError, json.JSONDecodeError):
        return code, None


class PolishingController:
    def __init__(self, speed_rad_s: float, arm: ArmSelection) -> None:
        self.speed = speed_rad_s
        self.moving_joints = (
            RIGHT_ARM
            if arm == "right"
            else LEFT_ARM
            if arm == "left"
            else LEFT_ARM + RIGHT_ARM
        )
        inactive_arm = (
            LEFT_ARM if arm == "right" else RIGHT_ARM if arm == "left" else ()
        )
        self.sdk_joints = self.moving_joints + inactive_arm + HELD_JOINTS
        self.stop_event = threading.Event()
        self.state_ready = threading.Event()
        self.lock = threading.Lock()
        self.last_state_time = 0.0
        self.measured: dict[int, float] = {}
        self.commanded: dict[int, float] = {}
        self.weight = 0.0
        self.command = unitree_hg_msg_dds__LowCmd_()
        self.publisher = ChannelPublisher("rt/arm_sdk", LowCmd_)
        self.subscriber = ChannelSubscriber("rt/lowstate", LowState_)
        self.crc = CRC()

    def initialize(self) -> None:
        self.publisher.Init()
        self.subscriber.Init(self._handle_state, 10)
        if not self.state_ready.wait(5.0):
            raise RuntimeError("No rt/lowstate sample received within 5 seconds")
        with self.lock:
            self.commanded = dict(self.measured)
            for joint in self.sdk_joints:
                motor = self.command.motor_cmd[joint.index]
                motor.tau = 0.0
                motor.q = self.commanded[joint.index]
                motor.dq = 0.0
                motor.kp = joint.kp
                motor.kd = joint.kd

    def _handle_state(self, message: LowState_) -> None:
        with self.lock:
            self.last_state_time = time.monotonic()
            self.measured = {
                joint.index: float(message.motor_state[joint.index].q)
                for joint in self.sdk_joints
            }
            self.state_ready.set()

    def _write(self) -> None:
        with self.lock:
            for joint in self.sdk_joints:
                self.command.motor_cmd[joint.index].q = self.commanded[joint.index]
            self.command.mode_pr = round(self.weight * 100.0)
            self.command.crc = self.crc.Crc(self.command)
        self.publisher.Write(self.command)

    def ramp_weight(self, target: float) -> bool:
        steps = max(1, round(WEIGHT_RAMP_DURATION / CONTROL_PERIOD))
        start = self.weight
        next_tick = time.monotonic()
        for step in range(steps):
            if self.stop_event.is_set() and target > 0.0:
                return False
            self.weight = start + (target - start) * ((step + 1) / steps)
            self._write()
            next_tick += CONTROL_PERIOD
            time.sleep(max(0.0, next_tick - time.monotonic()))
        return True

    def move_to(self, target: dict[int, float]) -> bool:
        with self.lock:
            start = {
                joint.index: self.commanded[joint.index]
                for joint in self.moving_joints
            }
        maximum_distance = max(
            abs(target[joint.index] - start[joint.index])
            for joint in self.moving_joints
        )
        duration = MINIMUM_JERK_PEAK_SLOPE * maximum_distance / self.speed
        if duration == 0.0:
            self._write()
            return True

        start_time = time.monotonic()
        next_tick = start_time
        while not self.stop_event.is_set():
            now = time.monotonic()
            elapsed_ratio = min(1.0, (now - start_time) / duration)
            ratio = 10 * elapsed_ratio**3 - 15 * elapsed_ratio**4 + 6 * elapsed_ratio**5
            with self.lock:
                if now - self.last_state_time > STATE_TIMEOUT:
                    raise RuntimeError("rt/lowstate timed out")
                for joint in self.moving_joints:
                    self.commanded[joint.index] = start[joint.index] + ratio * (
                        target[joint.index] - start[joint.index]
                    )
            self._write()
            if elapsed_ratio >= 1.0:
                return True
            next_tick += CONTROL_PERIOD
            self.stop_event.wait(max(0.0, next_tick - time.monotonic()))
        return False

    def hold(self, duration: float) -> bool:
        deadline = time.monotonic() + duration
        next_tick = time.monotonic()
        while not self.stop_event.is_set() and time.monotonic() < deadline:
            with self.lock:
                if time.monotonic() - self.last_state_time > STATE_TIMEOUT:
                    raise RuntimeError("rt/lowstate timed out")
            self._write()
            next_tick += CONTROL_PERIOD
            self.stop_event.wait(max(0.0, next_tick - time.monotonic()))
        return not self.stop_event.is_set()

    def close(self) -> None:
        self.ramp_weight(0.0)
        self.subscriber.Close()
        self.publisher.Close()


def run_polishing_action(
    client,
    *,
    arm: ArmSelection = "right",
    speed_deg_s: float = 120.0,
    hold_duration: float = 0.05,
    stop_event: threading.Event | None = None,
) -> int:
    """Run polishing until ``stop_event`` is set, then release ArmSdk control."""
    if arm not in {"left", "right", "both"}:
        raise ValueError("arm must be 'left', 'right', or 'both'")
    if not 100.0 <= speed_deg_s <= 150.0:
        raise ValueError("speed_deg_s must be between 100 and 150")
    if not 0.05 <= hold_duration <= 0.5:
        raise ValueError("hold_duration must be between 0.05 and 0.5")

    code, fsm_id = _fsm_id(client)
    if code != 0 or fsm_id != LOCOMOTION_FSM_ID:
        raise RuntimeError(
            f"Expected FSM {LOCOMOTION_FSM_ID}; received code={code}, fsm={fsm_id}."
        )

    pose_1, pose_2, pose_3 = _action_poses(arm)
    controller = PolishingController(math.radians(speed_deg_s), arm)
    if stop_event is not None:
        controller.stop_event = stop_event
    try:
        controller.initialize()
    except Exception:
        controller.subscriber.Close()
        controller.publisher.Close()
        raise
    try:
        if controller.ramp_weight(1.0) and controller.move_to(pose_1):
            controller.hold(hold_duration)
        while not controller.stop_event.is_set():
            for pose in (pose_2, pose_3):
                if not controller.move_to(pose) or not controller.hold(hold_duration):
                    break
            else:
                continue
            break
    finally:
        controller.close()
    return 0
