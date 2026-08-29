#!/usr/bin/env python3
"""Interactively list and switch R1 services through the Unitree DDS API.

Run with only a network interface to open the interactive menu.  The original
``list``, ``on`` and ``off`` commands are also available for automation.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow this utility to run directly from its own folder without requiring the
# SDK package to be installed site-wide.
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from unitree_sdk2py.core.channel import ChannelFactoryInitialize
from unitree_sdk2py.go2.robot_state.robot_state_api import (
    ROBOT_STATE_ERR_SERVICE_PROTECTED,
)
from unitree_sdk2py.go2.robot_state.robot_state_client import RobotStateClient


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("network_interface", help="interface connected to the R1")
    parser.add_argument(
        "action",
        nargs="?",
        choices=("list", "on", "off"),
        help="omit to open the interactive service menu",
    )
    parser.add_argument(
        "service",
        nargs="?",
        help="exact service name returned by the list action",
    )
    return parser.parse_args()


def get_services(client: RobotStateClient):
    code, services = client.ServiceList()
    if code != 0 or services is None:
        raise RuntimeError(f"ServiceList failed with code {code}")
    return services


def status_label(status) -> str:
    """Translate the R1 service status: 0 is running and 1 is stopped."""
    if status is False or status == 0:
        return "ON"
    if status is True or status == 1:
        return "OFF"
    return str(status)


def print_services(services) -> list:
    ordered = sorted(services, key=lambda item: item.name.lower())
    print(f"\n{'#':>3}  {'SERVICE':<42} {'STATUS':<8} PROTECTED")
    print("-" * 70)
    for index, service in enumerate(ordered, start=1):
        print(
            f"{index:>3}  {service.name:<42} "
            f"{status_label(service.status):<8} "
            f"{'yes' if service.protect else 'no'}"
        )
    return ordered


def switch_service(client: RobotStateClient, service, enable: bool) -> None:
    if service.protect:
        raise RuntimeError(
            f"Service {service.name!r} is protected and cannot be switched."
        )

    code = client.ServiceSwitch(service.name, enable)
    if code == ROBOT_STATE_ERR_SERVICE_PROTECTED:
        raise RuntimeError(f"Robot reports that {service.name!r} is protected")
    if code != 0:
        raise RuntimeError(f"ServiceSwitch failed with code {code}")


def interactive_menu(client: RobotStateClient) -> int:
    while True:
        services = print_services(get_services(client))
        print("\nSelect a service number, [r]efresh, or [q]uit.")
        choice = input("> ").strip().lower()
        if choice in {"q", "quit", "exit"}:
            return 0
        if choice in {"r", "refresh"}:
            continue

        try:
            service = services[int(choice) - 1]
            if int(choice) < 1:
                raise IndexError
        except (ValueError, IndexError):
            print("Invalid selection. Enter one of the service numbers shown.")
            continue

        if service.protect:
            print(f"{service.name!r} is protected and cannot be switched.")
            continue

        current = status_label(service.status)
        requested = input(
            f"{service.name} is {current}. Enter on, off, or cancel: "
        ).strip().lower()
        if requested in {"c", "cancel", ""}:
            continue
        if requested not in {"on", "off"}:
            print("Invalid action. Enter 'on', 'off', or 'cancel'.")
            continue

        enable = requested == "on"
        confirmation = input(
            f"Confirm switching {service.name!r} {requested.upper()}? [y/N]: "
        ).strip().lower()
        if confirmation not in {"y", "yes"}:
            print("Cancelled.")
            continue

        try:
            switch_service(client, service, enable)
            refreshed = get_services(client)
            state = next(
                (item for item in refreshed if item.name == service.name), None
            )
            reported = status_label(state.status) if state is not None else "unknown"
            print(
                f"{service.name}: requested {requested.upper()}, "
                f"reported {reported}."
            )
        except RuntimeError as error:
            print(f"Error: {error}", file=sys.stderr)


def main() -> int:
    args = parse_args()
    if args.action in {"on", "off"} and not args.service:
        raise SystemExit("on/off requires the exact service name from list")

    print(f"DDS interface: {args.network_interface}")
    ChannelFactoryInitialize(0, args.network_interface)
    client = RobotStateClient()
    client.SetTimeout(3.0)
    client.Init()

    if args.action is None:
        return interactive_menu(client)

    services = get_services(client)
    if args.action == "list":
        print_services(services)
        return 0

    matching = [service for service in services if service.name == args.service]
    if not matching:
        available = ", ".join(service.name for service in services)
        raise SystemExit(
            f"Service {args.service!r} was not returned by the robot. "
            f"Available services: {available}"
        )
    service = matching[0]
    enable = args.action == "on"
    try:
        switch_service(client, service, enable)
    except RuntimeError as error:
        raise SystemExit(str(error)) from error

    refreshed = get_services(client)
    state = next((item for item in refreshed if item.name == service.name), None)
    print(
        f"Requested {service.name}: {'ON' if enable else 'OFF'}; "
        f"reported status={status_label(state.status) if state is not None else 'unknown'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
