#!/usr/bin/env python3
"""Print the stereo center-clearance distance without starting the web UI."""

from __future__ import annotations

import argparse
import signal
import sys
import time
from pathlib import Path


# Support both ``python backend/print_center_clearance.py`` and ``python -m``.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.robot_stereo_detection import (  # noqa: E402
    CENTER_CLEARANCE_HEIGHT,
    CENTER_CLEARANCE_WIDTH,
    CENTER_CLEARANCE_X,
    CENTER_CLEARANCE_Y,
    RobotStereoDetectionService,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Print center-clearance distance from the R1 stereo cameras."
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=0.25,
        help="Minimum seconds between printed measurements (default: 0.25).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.interval <= 0:
        print("--interval must be greater than zero", file=sys.stderr)
        return 2

    stop_requested = False

    def request_stop(_signum: int, _frame: object) -> None:
        nonlocal stop_requested
        stop_requested = True

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    detector = RobotStereoDetectionService(enable_object_detection=False)
    print(
        "Center clearance region: "
        f"x={CENTER_CLEARANCE_X}, y={CENTER_CLEARANCE_Y}, "
        f"width={CENTER_CLEARANCE_WIDTH}, height={CENTER_CLEARANCE_HEIGHT}px"
    )
    print(
        f"Stereo ports: left={detector.left_port}, right={detector.right_port}. "
        "Press Ctrl+C to stop."
    )

    last_sequence = -1
    last_printed_at = 0.0
    try:
        detector.start("depth")
        while not stop_requested:
            status = detector.status()
            if status["state"] == "error":
                print(f"ERROR: {status['error']}", file=sys.stderr)
                return 1

            sequence = int(status.get("frame_sequence", 0))
            now = time.monotonic()
            if sequence != last_sequence and now - last_printed_at >= args.interval:
                distance = status.get("obstacle_distance_m")
                pair_delta = status.get("pair_delta_ms")
                if isinstance(distance, (int, float)):
                    print(
                        f"CENTER CLEARANCE: {float(distance):.3f} m "
                        f"| pair delta: {pair_delta} ms",
                        flush=True,
                    )
                else:
                    print(
                        f"CENTER CLEARANCE: unavailable | pair delta: {pair_delta} ms",
                        flush=True,
                    )
                last_sequence = sequence
                last_printed_at = now
            time.sleep(0.02)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        detector.stop()

    print("Center-clearance monitor stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
