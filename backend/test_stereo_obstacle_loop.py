#!/usr/bin/env python3
"""Test a simple stereo-depth obstacle avoidance loop on the Unitree R1.

The decision uses raw stereo depth in the central forward image region; it
does not depend on YOLO object recognition. This remains a functional test,
not a replacement for a certified collision sensor.

The script is dry-run by default.  Pass --live to send locomotion commands.
Stop at any time with Ctrl-C; live mode sends a final stop command.
"""

from __future__ import annotations

import argparse
import signal
import time
from pathlib import Path
import sys
from typing import Any


# Allow both ``python backend/test_stereo_obstacle_loop.py`` and ``python -m``.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.robot_control import (
    LINEAR_SPEED,
    TURN_SPEED,
    RobotControlError,
    RobotControlService,
)
from backend.robot_stereo_detection import (
    RobotStereoDetectionService,
    RobotStereoError,
)


DEFAULT_THRESHOLD_M = 0.50
DEFAULT_POLL_SECONDS = 0.10
DEFAULT_START_TIMEOUT_SECONDS = 60.0
DEFAULT_FRAME_TIMEOUT_SECONDS = 5.0
DEFAULT_SETTLE_SECONDS = 0.75
MAX_STEP_DISTANCE_M = 0.50
MAX_TURN_ANGLE_DEG = 90.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Turn right when stereo depth is within the threshold; "
            "otherwise move forward for one bounded robot command."
        )
    )
    parser.add_argument(
        "--threshold-m",
        type=float,
        default=DEFAULT_THRESHOLD_M,
        help="Obstacle distance threshold (default: 0.50 m).",
    )
    parser.add_argument(
        "--step-distance-m",
        type=float,
        default=0.15,
        help="Forward distance per clear-path step (default: 0.15 m; max: 0.50 m).",
    )
    parser.add_argument(
        "--turn-angle-deg",
        type=float,
        default=30.0,
        help="Right turn angle when blocked (default: 30 degrees; max: 90).",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Actually move the robot. Without this flag, only print decisions.",
    )
    parser.add_argument(
        "--max-actions",
        type=int,
        default=0,
        help="Stop after this many decisions; 0 loops until Ctrl-C (default: 0).",
    )
    parser.add_argument(
        "--settle-seconds",
        type=float,
        default=DEFAULT_SETTLE_SECONDS,
        help="Wait after each movement before evaluating a new frame.",
    )
    parser.add_argument(
        "--frame-timeout-seconds",
        type=float,
        default=DEFAULT_FRAME_TIMEOUT_SECONDS,
        help="Maximum wait for a fresh connected stereo frame.",
    )
    parser.add_argument(
        "--start-timeout-seconds",
        type=float,
        default=DEFAULT_START_TIMEOUT_SECONDS,
        help="Maximum wait for the detector's first connected frame.",
    )
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    if args.threshold_m <= 0:
        raise ValueError("--threshold-m must be greater than zero")
    if args.max_actions < 0:
        raise ValueError("--max-actions cannot be negative")
    if not 0 < args.step_distance_m <= MAX_STEP_DISTANCE_M:
        raise ValueError(
            f"--step-distance-m must be greater than 0 and at most {MAX_STEP_DISTANCE_M:.2f} m"
        )
    if not 0 < args.turn_angle_deg <= MAX_TURN_ANGLE_DEG:
        raise ValueError(
            f"--turn-angle-deg must be greater than 0 and at most {MAX_TURN_ANGLE_DEG:.0f} degrees"
        )
    if args.settle_seconds < 0:
        raise ValueError("--settle-seconds cannot be negative")
    if args.frame_timeout_seconds <= 0 or args.start_timeout_seconds <= 0:
        raise ValueError("timeout values must be greater than zero")


def wait_for_fresh_frame(
    detector: RobotStereoDetectionService,
    after_sequence: int,
    timeout_seconds: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_status: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last_status = detector.status()
        if last_status.get("state") == "error":
            raise RobotStereoError(str(last_status.get("error") or "unknown error"))
        if (
            last_status.get("connected")
            and int(last_status.get("frame_sequence", 0)) > after_sequence
        ):
            return last_status
        time.sleep(DEFAULT_POLL_SECONDS)
    detail = last_status.get("error") or last_status.get("state") or "no status"
    raise RobotStereoError(f"Timed out waiting for a fresh stereo frame: {detail}")


def choose_action(
    status: dict[str, Any], threshold_m: float
) -> tuple[str, str]:
    distance = status.get("obstacle_distance_m")
    if not isinstance(distance, (int, float)) or distance < 0:
        return "turn_right", "no reliable depth in the forward region"
    distance_m = float(distance)
    if distance_m <= threshold_m:
        return "turn_right", f"depth obstacle is {distance_m:.2f} m away"
    return "forward", f"forward-region depth is {distance_m:.2f} m"


def movement_duration(action: str, args: argparse.Namespace) -> float:
    """Convert the requested distance/angle to time at the configured speed."""
    if action == "forward":
        return args.step_distance_m / LINEAR_SPEED
    if action == "turn_right":
        return args.turn_angle_deg * 3.141592653589793 / 180.0 / TURN_SPEED
    raise ValueError(f"Cannot calculate duration for unsupported movement: {action}")


def execute_timed_movement(
    controller: RobotControlService,
    action: str,
    duration_seconds: float,
) -> None:
    """Issue a bounded velocity command, then explicitly stop its motion."""
    vx, vy, omega = {
        "forward": (LINEAR_SPEED, 0.0, 0.0),
        "turn_right": (0.0, 0.0, -TURN_SPEED),
    }[action]
    controller.execute_velocity(vx, vy, omega, duration_seconds)


def main() -> int:
    args = parse_args()
    try:
        validate_args(args)
    except ValueError as exc:
        print(f"Argument error: {exc}", file=sys.stderr)
        return 2

    stop_requested = False

    def request_stop(_signum: int, _frame: object) -> None:
        nonlocal stop_requested
        stop_requested = True

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    detector = RobotStereoDetectionService(enable_object_detection=False)
    controller = RobotControlService() if args.live else None
    last_sequence = 0
    action_count = 0
    mode = "LIVE" if args.live else "DRY RUN"
    print(f"Starting stereo obstacle loop in {mode}; threshold={args.threshold_m:.2f} m")
    print(
        f"Step={args.step_distance_m:.2f} m; right turn={args.turn_angle_deg:.1f} degrees"
    )
    print(f"Forward depth region (left, top, right, bottom): {detector.obstacle_region}")

    try:
        detector.start()
        status = wait_for_fresh_frame(detector, 0, args.start_timeout_seconds)
        last_sequence = int(status["frame_sequence"])
        print("Stereo detector connected. Press Ctrl-C to stop.")

        while not stop_requested and (
            args.max_actions == 0 or action_count < args.max_actions
        ):
            status = wait_for_fresh_frame(
                detector, last_sequence, args.frame_timeout_seconds
            )
            last_sequence = int(status["frame_sequence"])
            action, reason = choose_action(status, args.threshold_m)
            action_count += 1
            print(f"[{action_count}] {action}: {reason}", flush=True)

            if controller is not None:
                duration_seconds = movement_duration(action, args)
                execute_timed_movement(controller, action, duration_seconds)
                if args.settle_seconds:
                    time.sleep(args.settle_seconds)
                # Do not decide from frames captured while the robot was moving
                # or during the post-motion settling interval.
                last_sequence = int(detector.status().get("frame_sequence", last_sequence))
            else:
                # Keep dry-run logs readable and avoid consuming frames at full FPS.
                time.sleep(max(args.settle_seconds, 0.25))

    except (RobotStereoError, RobotControlError) as exc:
        print(f"Stopped because of an error: {exc}", file=sys.stderr)
        return 1
    finally:
        if controller is not None:
            try:
                controller.execute("stop")
                print("Final robot stop command sent.")
            except RobotControlError as exc:
                print(f"WARNING: final robot stop failed: {exc}", file=sys.stderr)
        detector.stop()

    print("Obstacle loop stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
