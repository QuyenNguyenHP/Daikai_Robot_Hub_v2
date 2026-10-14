# Center Clearance Calculation

This document describes the current center-clearance algorithm used by the R1 Distance Monitor and Autonomous Walk features.

## Purpose

Center clearance is an estimate of the nearest **reliable local surface** inside a selected image region. It is not the raw minimum depth pixel. A raw minimum would react strongly to a single bad stereo match, so the implementation requires a nearby group of valid depth pixels before reporting a close obstacle.

The result is exposed as `obstacle_distance_m` and is used by Autonomous Walk to decide whether to move forward or turn right.

## Processing pipeline

```text
Left RTP camera (UDP 5002) ─┐
                            ├─ Pair frames ─ Rectify ─ StereoSGBM ─ Filter disparity
Right RTP camera (UDP 5003) ┘                                      │
                                                                  ▼
                                                     Reproject disparity to 3D
                                                                  │
                                                                  ▼
                                                     Select clearance rectangle
                                                                  │
                                                                  ▼
                                                   Find nearest reliable local cell
                                                                  │
                                                                  ▼
                                                     Center clearance in metres
```

## 1. Stereo video input

The service receives two RTP/H.264 streams:

- Left camera: UDP port `5002`
- Right camera: UDP port `5003`
- Default frame size: `544 × 448` pixels
- Maximum permitted local arrival-time difference: `80 ms`

The two newest frames are accepted as a pair only when their decoder arrival-time difference is within the configured limit. The current pair difference is shown in the UI as `Pair delta ms`.

The pairing uses local decoder arrival time, not the original RTP source timestamp. This is an experimental limitation for moving scenes.

## 2. Stereo calibration and rectification

Calibration is loaded from:

```text
backend/r1_yolo_world_stereo/r1_stereo_calibration.npz
```

It contains:

- Left and right camera intrinsic matrices
- Lens distortion coefficients
- Rotation and translation between the cameras
- Calibration image size

OpenCV `stereoRectify()` creates rectification transforms and the reprojection matrix `Q`. Both images are remapped so corresponding physical points should appear on the same image row.

Incorrect calibration, camera movement after calibration, or poor rectification can produce incorrect depth even when the software is working normally.

## 3. Disparity calculation

The rectified images are converted to grayscale and processed by OpenCV StereoSGBM.

Current defaults:

| Setting | Value |
|---|---:|
| Minimum disparity | `0` |
| Number of disparities | `64` |
| Block size | `3` |
| Uniqueness ratio | `10` |
| Left/right disparity difference | `1` |
| Speckle window size | `100` |
| Speckle range | `2` |
| Mode | `SGBM_3WAY` |

Conceptually, depth is inversely proportional to disparity:

```text
Z ≈ focal_length × stereo_baseline / disparity
```

A large disparity normally means a nearby surface. A small disparity normally means a distant surface. The implementation does not calculate this formula manually; it uses OpenCV `reprojectImageTo3D(disparity, Q)` so the calibration parameters are applied consistently.

The dark strip on the left edge of the disparity image is expected. StereoSGBM cannot calculate valid disparity for part of the left boundary because it must search horizontally for corresponding pixels.

## 4. Disparity consistency filtering

Raw disparity can contain false close points caused by low texture, reflections, shadows, repeating patterns, occlusion boundaries, or imperfect synchronization.

The service applies a `5 × 5` median filter. A disparity pixel remains valid only when:

```text
raw disparity > 0.5
local median disparity > 0.5
absolute(raw disparity - local median disparity) <= 2.0 pixels
```

The `2.0` threshold is controlled by:

```text
R1_STEREO_DISPARITY_CONSISTENCY_PX
```

Rejected disparity pixels are assigned `-1` and are excluded from clearance calculation.

## 5. Clearance region

The selected region is configured in pixels near the top of `backend/robot_stereo_detection.py`:

```python
CENTER_CLEARANCE_X = 300
CENTER_CLEARANCE_Y = 180
CENTER_CLEARANCE_WIDTH = 220
CENTER_CLEARANCE_HEIGHT = 260
```

`X` and `Y` specify the top-left corner. `WIDTH` and `HEIGHT` specify the box size.

With the current values, the region covers:

```text
x = 300 through 519
y = 180 through 439
```

inside the `544 × 448` frame. The backend validates that the complete rectangle remains inside the image.

The yellow rectangle shown by Distance Monitor is generated from this same region. Pixels outside it do not affect Autonomous Walk clearance decisions.

## 6. Valid depth samples

Inside the selected rectangle, a sample is valid only when all conditions below are true:

```text
distance is finite
disparity > 0.5
distance >= 0.15 m
distance <= 15.0 m
```

The default distance mode is optical-axis `Z`. Therefore the reported value is forward distance along the camera optical axis, not full Euclidean distance from the camera.

If fewer than `100` valid samples exist in the whole rectangle, clearance is reported as unavailable.

## 7. Nearest reliable local surface

The algorithm intentionally does not use:

```python
minimum_distance = distances.min()
```

One incorrect stereo pixel could otherwise report an extremely close obstacle.

Instead, the selected rectangle is divided into local cells:

```python
CENTER_CLEARANCE_CELL_SIZE_PX = 16
CENTER_CLEARANCE_MIN_VALID_RATIO = 0.40
```

For every `16 × 16` cell:

1. Count its valid depth pixels.
2. Ignore the cell when fewer than `40%` of its pixels are valid.
3. Calculate the median distance of the valid pixels in an accepted cell.
4. Add that median to the list of reliable local distances.

The final center clearance is:

```text
minimum(median distance of every accepted local cell)
```

This means the output is the nearest locally supported surface, rather than the nearest individual pixel.

### Example

Assume the rectangle contains:

- One isolated false pixel at `0.18 m`
- A populated local cell representing an obstacle at approximately `0.45 m`
- Background cells between `1.2 m` and `3.0 m`

The isolated `0.18 m` pixel does not satisfy the cell-validity requirement. The populated obstacle cell is accepted, so the result is approximately:

```text
CENTER CLEARANCE: 0.45 m
```

### Sparse fallback

If the rectangle contains at least `100` valid samples but no local cell meets the `40%` requirement, the algorithm falls back to the configured low percentile. Its default is percentile `10`:

```text
R1_STEREO_OBSTACLE_PERCENTILE=10
```

## 8. Distance-monitor colors

The displayed depth image uses OpenCV's Turbo color map applied to normalized disparity. It is primarily a visualization of disparity, not a calibrated color-to-metre scale.

- Bright/red areas generally have larger disparity and may be nearer.
- Blue/purple areas generally have smaller disparity and may be farther away.
- Dark gray/black areas have invalid or rejected disparity.

The color of one pixel should not be interpreted as the clearance result. Clearance is calculated from filtered metric 3D points and the reliable-cell procedure described above.

## 9. Autonomous Walk decision

For every movement decision, Autonomous Walk collects `8` consecutive fresh stereo frames. Each frame produces one spatially filtered `obstacle_distance_m` value using the reliable-cell procedure above. All eight values must be valid.

The temporal clearance used for the decision is:

```text
median(clearance frame 1 ... clearance frame 8)
```

The median suppresses occasional high or low measurements without allowing one noisy frame to control the movement. If any of the eight consecutive frames has unreliable depth, or a fresh frame times out, the robot stops instead of guessing.

The decision is:

```text
clearance unavailable
    → stop with an error

clearance < configured obstacle-clearance threshold
    → turn right for one bounded movement

clearance >= configured obstacle-clearance threshold
    → move forward for one bounded movement
```

If the path remains blocked after `Maximum right turns`, Autonomous Walk stops and reports a blocked state.

Frames captured during the movement are not immediately used for the next decision. After each non-final movement, the service waits `0.6 seconds` and then collects eight new frames.

## 10. Tuning guidance

### Detect smaller obstacles

Reduce cell size or the minimum valid ratio:

```python
CENTER_CLEARANCE_CELL_SIZE_PX = 12
CENTER_CLEARANCE_MIN_VALID_RATIO = 0.30
```

This increases sensitivity but also increases false-obstacle risk.

### Reject more stereo noise

Increase cell size or the minimum valid ratio:

```python
CENTER_CLEARANCE_CELL_SIZE_PX = 20
CENTER_CLEARANCE_MIN_VALID_RATIO = 0.50
```

This improves stability but can miss narrow obstacles.

### Change the physical travel corridor

Modify:

```python
CENTER_CLEARANCE_X
CENTER_CLEARANCE_Y
CENTER_CLEARANCE_WIDTH
CENTER_CLEARANCE_HEIGHT
```

The rectangle should represent the space the robot's body needs to traverse. Avoid including excessive floor, ceiling, non-overlapping stereo boundaries, or areas outside the robot's path.

## Safety limitations

This stereo pipeline is not a safety-rated collision sensor. Depth may fail because of:

- Textureless or reflective surfaces
- Glass, mirrors, or direct sunlight
- Repeating visual patterns
- Camera vibration or motion blur
- Incorrect calibration
- Left/right frame timing differences
- Objects visible to only one camera
- Very thin or very small obstacles

Use the robot only in a controlled, flat area and keep the hardware emergency stop available.

## Relevant source files

- `backend/robot_stereo_detection.py` — filtering, region selection, reliable-cell calculation, status and visualization
- `backend/r1_yolo_world_stereo/r1_stereo_common.py` — RTP capture, rectification, StereoSGBM and 3D reprojection
- `backend/robot_auto_walk.py` — movement decision logic
- `backend/print_center_clearance.py` — standalone terminal clearance monitor

