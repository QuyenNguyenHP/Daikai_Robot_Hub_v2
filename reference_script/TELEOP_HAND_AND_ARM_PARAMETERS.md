# `teleop_hand_and_arm.py` Parameter Reference

This document lists every command-line parameter supported by
`teleop/teleop_hand_and_arm.py`, including the recommended configuration for a
physical Unitree R1-A5 using its integrated camera and Meta Quest 3
controllers.

> [!CAUTION]
> Keep the robot in direct view, clear the operating area, and keep the physical
> remote and emergency stop ready. On the currently tested R1 firmware, do not
> use `--motion`: arm SDK control enters FSM mode `816`, where locomotion
> velocity commands are not accepted.

## Recommended R1-A5 command

```bash
conda activate tv
cd /home/daikai/xr_teleoperate/teleop

python teleop_hand_and_arm.py \
  --frequency=30 \
  --input-mode=controller \
  --display-mode=immersive \
  --arm=R1_A5 \
  --img-server-ip=127.0.0.1 \
  --network-interface=enxa0cec86d95d6
```

Replace `enxa0cec86d95d6` with the Ethernet interface connected to the robot:

```bash
ip -br -4 address
```

Use the interface with the `192.168.123.x` robot-network address, not the Quest
Wi-Fi interface.

## R1-A5 command with images turned off

To run arm teleoperation without starting or connecting to Teleimager, use both
`--no-image-server` and `--display-mode=pass-through`:

```bash
conda activate tv
cd /home/daikai/xr_teleoperate/teleop

python teleop_hand_and_arm.py \
  --frequency=30 \
  --input-mode=controller \
  --display-mode=pass-through \
  --arm=R1_A5 \
  --network-interface=enxa0cec86d95d6 \
  --no-image-server
```

In this mode, the Quest pass-through view remains available, but robot head and
wrist camera images are not acquired or displayed. The `--img-server-ip` option
is unnecessary, and recording cannot be enabled because no camera frames are
available.

## Complete parameter summary

| Parameter               | Available values                                                                     | Default                             | R1-A5 recommendation                                       |
| ----------------------- | ------------------------------------------------------------------------------------ | ----------------------------------- | ---------------------------------------------------------- |
| `--frequency`         | Floating-point frequency, such as`15`, `30`, or `60`                           | `30.0`                            | `30`                                                     |
| `--input-mode`        | `hand`, `controller`                                                             | `hand`                            | `controller`                                             |
| `--display-mode`      | `immersive`, `ego`, `pass-through`                                             | `immersive`                       | `immersive`                                              |
| `--arm`               | `G1_29`, `G1_23`, `H1_2`, `H1`, `H2`, `R1_A5`, `R1_A7`                 | `G1_29`                           | `R1_A5`                                                  |
| `--ee`                | `dex1`, `dex1_internal`, `dex3`, `inspire_ftp`, `inspire_dfx`, `brainco` | None                                | Omit initially                                             |
| `--img-server-ip`     | IP address or hostname                                                               | `192.168.123.164`                 | `127.0.0.1`                                              |
| `--network-interface` | Interface name such as`eth0` or `enxa0cec86d95d6`                                | None                                | Robot Ethernet interface                                   |
| `--no-image-server`   | Boolean flag: include it to turn off robot-camera transport                          | Images enabled                      | Add with`--display-mode=pass-through` to turn off images |
| `--motion`            | Boolean flag: include it to enable                                                   | Disabled                            | **Omit: currently unsupported with R1-A5**           |
| `--headless`          | Boolean flag: include it to enable                                                   | Disabled                            | Omit                                                       |
| `--sim`               | Boolean flag: include it to enable                                                   | Disabled                            | Omit for a physical robot                                  |
| `--ipc`               | Boolean flag: include it to enable                                                   | Disabled                            | Omit for normal keyboard control                           |
| `--record`            | Boolean flag: include it to enable                                                   | Disabled                            | Optional                                                   |
| `--task-dir`          | Writable directory path                                                              | `./utils/data/`                   | Set when recording if needed                               |
| `--task-name`         | Free-form text                                                                       | `pick cube`                       | Set when recording                                         |
| `--task-goal`         | Free-form text                                                                       | `pick up cube.`                   | Set when recording                                         |
| `--task-desc`         | Free-form text                                                                       | `task description`                | Set when recording                                         |
| `--task-steps`        | Free-form text                                                                       | `step1: do this; step2: do that;` | Set when recording                                         |
| `-h`, `--help`      | Display command help and exit                                                        | —                                  | Diagnostic only                                            |

## Parameter details

### `--frequency`

Sets the main control-loop and recording frequency in Hz.

```bash
--frequency=30
```

The parser accepts any floating-point value, but zero, negative, or excessively
high values are not valid practical configurations. Start with `30`.

### `--input-mode`

Available values:

```text
hand
controller
```

- `hand` uses Quest hand tracking to control the arms.
- `controller` uses Quest controllers to control the arms. Although the common
  code contains a joystick locomotion path, it does not currently work with
  R1-A5 in FSM mode `816`.

Use this for R1-A5 controller-pose arm control:

```bash
--input-mode=controller
```

### `--display-mode`

Available values:

```text
immersive
ego
pass-through
```

- `immersive` displays the robot-camera view as the main VR view.
- `ego` uses headset pass-through with a smaller first-person camera window.
- `pass-through` uses headset pass-through only.

Use `immersive` for the R1 integrated-camera setup.

### `--arm`

Available values:

```text
G1_29
G1_23
H1_2
H1
H2
R1_A5
R1_A7
```

Use `--arm=R1_A5` for the R1 with 5-DoF arms.

### `--ee`

Available end-effector values:

```text
dex1
dex1_internal
dex3
inspire_ftp
inspire_dfx
brainco
```

Omit this parameter if the R1-A5 does not have a supported end effector.

Controller-input limitations:

- `dex3`, `inspire_ftp`, and `inspire_dfx` do not support controller input.
- `dex1` supports controller input.
- `brainco` provides separate hand- and controller-input implementations.
- `dex1_internal` is restricted to `G1_29` and cannot be used for R1-A5.
- `dex1_internal` also cannot currently be combined with `--motion`.

### `--img-server-ip`

Sets the address of the Teleimager service.

- Use `127.0.0.1` when Teleimager runs on the same Host.
- Use the remote computer's reachable address when Teleimager runs elsewhere.

The integrated-camera guide runs Teleimager on the same Host, so use
`--img-server-ip=127.0.0.1`.

### `--network-interface`

Selects the interface used for Unitree DDS communication. Examples include:

```text
eth0
enp3s0
eno1
enxa0cec86d95d6
```

If this parameter is omitted, the program uses the default interface, which
may be incorrect on a Host connected to the robot over Ethernet and the Quest
over Wi-Fi.

### Boolean mode flags

The following options are flags and do not accept values:

```text
--no-image-server
--motion
--headless
--sim
--ipc
--record
```

Correct syntax is `--motion`; do not use `--motion=true`.

- `--motion` requests arm teleoperation alongside the locomotion controller on
  supported robots. It is currently unsupported for R1-A5/R1-A7 in this setup.
- `--headless` runs without the normal display/UI path.
- `--sim` selects the Isaac simulation configuration instead of a physical robot.
- `--ipc` uses IPC commands instead of the normal SSH keyboard handler.
- `--record` enables episode recording.
- `--no-image-server` disables Teleimager and camera acquisition.

Constraints:

- `--no-image-server` requires `--display-mode=pass-through`.
- `--no-image-server` cannot be combined with `--record`.
- Do not use `--no-image-server` when displaying the integrated robot camera.
- Do not use `--sim` with the physical R1.
- Do not combine R1-A5 with `--motion` on the currently tested firmware.

### Recording parameters

These parameters describe an episode when `--record` is enabled:

```bash
--record \
  --task-dir="./utils/data/" \
  --task-name="R1 mobile manipulation" \
  --task-goal="Walk to the table and manipulate the object" \
  --task-desc="R1-A5 controlled with Meta Quest controllers" \
  --task-steps="Walk to target; stop; manipulate object; return arms"
```

Use quotes around values containing spaces or shell punctuation.

## R1-A5 joystick locomotion limitation

The common teleoperation code maps the Quest controls as follows on supported
robot/firmware combinations:

- Left joystick forward/backward controls forward/backward walking.
- Left joystick left/right controls lateral movement.
- Right joystick left/right controls turning.
- Pressing both joysticks requests damping mode as a soft emergency stop.
- The right controller A button exits teleoperation.
- Translational and turning commands are limited to a magnitude of `0.3` in
  the current code.

These controls are for Meta Quest controllers. A generic USB joystick or
gamepad is not supported by this input path without additional input code.

They are not currently usable for simultaneous R1-A5 arm control and walking.
Publishing R1-A5 arm SDK commands changes the robot to FSM mode `816`; in that
mode, the tested firmware does not accept locomotion velocity commands. The
Quest controller poses can still control the arms when `--motion` is omitted.

## Startup checklist

1. Start the camera-only `robot_patch_pc1.service` on R1 PC1.
2. Start the UDP-to-`/dev/video10` GStreamer pipeline.
3. Start `teleimager-server` and wait until the head camera is ready.
4. Start `teleop_hand_and_arm.py` with the recommended command, without
   `--motion`.
5. Connect the Quest to `https://HOST_WIFI_IP:8012`.
6. Confirm that the camera video is live and has safe latency.
7. Clear the robot workspace and press `r` in the terminal to start control.

For the complete integrated-camera setup, see
[`README_R1_A5_INTEGRATED_CAMERA.md`](README_R1_A5_INTEGRATED_CAMERA.md).
