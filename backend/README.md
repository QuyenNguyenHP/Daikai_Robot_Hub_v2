# Backend Guide

This folder contains the FastAPI backend for **Daikai Robot Hub**. It supports
two image sources while keeping one shared face-recognition pipeline:

```text
Browser webcam -> POST /api/recognize --+
                                        +-> FaceService -> YuNet -> SFace
Unitree R1 -> RobotCameraService -------+
```

The browser owns the normal webcam. The backend never opens `/dev/video*`.
The backend owns the Unitree connection because the browser cannot talk to
Unitree DDS directly.

## Folder structure

```text
backend/
|-- __init__.py
|-- __main__.py
|-- app.py
|-- main.py
|-- common.py
|-- face_service.py
|-- robot_camera.py
|-- robot_battery.py
|-- robot_control.py
|-- robot_audio.py
|-- download_models.py
|-- models/
|   |-- face_detection_yunet_2023mar.onnx
|   `-- face_recognition_sface_2021dec.onnx
`-- README.md
```

The older `backend/src` programs are no longer part of the running app. Webcam
enrollment, recognition, and robot integrations now live behind the FastAPI
service in this folder.

## Entry points

### `__main__.py`

Command-line launcher for robot mode. It accepts the Unitree network interface,
sets `UNITREE_NETWORK_INTERFACE`, then starts Uvicorn with one worker.

From the project root:

```bash
python3 backend eth0
```

By default it listens on `0.0.0.0:8000`. You can override host and port:

```bash
python3 backend eth0 --host 127.0.0.1 --port 8000
```

This is the better launcher when you want the backend itself to set the robot
interface.

### `app.py`

Small development launcher. It adds the project root to `sys.path` and starts:

```bash
python backend/app.py
```

It always uses:

- `host="0.0.0.0"`
- `port=8000`
- `reload=True`

That makes it convenient for local development, but less ideal for Apache
reverse-proxy deployment on the Pi.

### `main.py`

Defines the FastAPI app, startup and shutdown lifecycle, request limits, CORS,
and every API endpoint.

During startup it creates exactly one instance of:

- `FaceService`
- `RobotCameraService`
- `RobotBatteryService`
- `RobotControlService`
- `RobotAudioService`
- `RobotServiceManager`
- `RobotStereoDetectionService`

During shutdown it stops the camera, battery subscriber, and robot control
service cleanly.

## Service modules

### `face_service.py`

Contains the shared face-recognition logic:

- decodes uploaded JPEG, PNG, and WebP images;
- detects faces with YuNet;
- aligns faces and extracts SFace embeddings;
- compares embeddings with cosine similarity;
- enrolls or updates a person;
- saves accepted face crops;
- lists enrolled people from metadata.

Both browser uploads and Unitree camera frames use this same service.

### `robot_camera.py`

Owns the Unitree camera connection. `RobotCameraService`:

1. reads `UNITREE_NETWORK_INTERFACE`;
2. delays importing `unitree_sdk2py` until robot mode is actually used;
3. initializes the DDS channel once;
4. starts one shared `VideoClient`;
5. captures JPEG frames in a background thread;
6. keeps only the newest frame;
7. exposes status, snapshot, and MJPEG stream helpers;
8. retries temporary camera-read failures.

If `UNITREE_NETWORK_INTERFACE` is missing, the service reports
`not_configured`.

### `robot_battery.py`

Subscribes to the Unitree battery DDS topic and keeps the latest reading ready
for API responses. It exposes battery status without making each HTTP request
wait on DDS traffic.

The topic defaults to the built-in battery topic, and you can override it with:

```bash
export UNITREE_BATTERY_TOPIC=...
```

Live robot video is proxied as MJPEG from the newest camera frame. To keep
small Jetson devices responsive, the browser stream defaults to 12 FPS and
live recognition downsizes wide frames to 640 pixels before inference. Both
limits are configurable before starting the backend:

```bash
export ROBOT_STREAM_FPS=12
export FACE_RECOGNITION_MAX_WIDTH=640
```

`ROBOT_STREAM_FPS` is clamped to 1-30 and
`FACE_RECOGNITION_MAX_WIDTH` is clamped to 320-1920.

### `robot_control.py`

Provides bounded locomotion control and FSM mode queries for the Unitree R1.

It supports these actions:

- `enable`
- `disable`
- `forward`
- `backward`
- `left`
- `right`
- `turn_left`
- `turn_right`
- `stop`

Only one control action can run at a time. Busy or invalid robot state
conditions are returned as HTTP `409` errors by the API layer.

### `robot_audio.py`

Owns the shared Unitree `AudioClient` used for English speech playback and RGB
LED control.
LED colors can optionally be kept active by resending the selected RGB value
at a configurable interval (`ROBOT_LED_KEEPALIVE_SECONDS`, default `0.5`).

Speech is sent directly to the robot with `AudioClient.TtsMaker()`. No local
TTS model, audio synthesizer, converter, or PCM streaming pipeline is used.
The speaker defaults to ID `1`; set `ROBOT_TTS_SPEAKER_ID` to override it.
Robot volume is controlled from `0` to `100` with `AudioClient.SetVolume()`.

Speech is limited to `200` characters per request, and only one speech request
can run at a time.

The Voice AI panel records the browser microphone and sends it through this
backend to the external `voice_ai_server`. Configure the backend before start:

```bash
export VOICE_AI_SERVER_URL=http://VOICE_AI_PC_IP:8000
export VOICE_AI_API_KEY=your-key-if-configured
export VOICE_AI_TIMEOUT_SECONDS=180
```

The backend requests JSON mode from `/v1/voice/chat`, converts the returned
24 kHz WAV to 16 kHz mono PCM, and sends it to the R1 speaker with
`AudioClient.PlayStream()`. The API key remains on the backend. Browser
microphone recording requires HTTPS when the frontend is opened from another
computer; browsers allow plain HTTP microphone access only on localhost.

### `robot_services.py`

Lists the services advertised by the Unitree robot-state API and switches
unprotected services on or off. Requests use exact service names returned by
the robot and are serialized so list and switch operations cannot overlap.
The tested R1 firmware reports service status in reverse (`0` means running),
so the backend inverts it by default. Set
`UNITREE_SERVICE_STATUS_INVERTED=0` for firmware that uses normal Boolean
status values.

### `robot_stereo_detection.py`

Adapts the R1 YOLO-World stereo reference pipeline for the web application. It
receives the left/right RTP streams, rectifies them, calculates disparity and
metric depth, runs YOLO-World, and publishes shared MJPEG detection and depth
views. The pipeline starts only when requested from the Object Distance page.
The YOLO model defaults to `backend/models/yolov8s-worldv2.pt`. Stereo helpers,
calibration, and the CLIP encoder default to
`backend/r1_yolo_world_stereo`. Override
those locations with `R1_STEREO_SOURCE_DIR`, `R1_STEREO_CALIBRATION`, and
`R1_YOLO_WORLD_MODEL`; prompts can be set with `R1_YOLO_WORLD_CLASSES`.

### `common.py`

Contains shared helpers for:

- project, model, and data paths;
- metadata JSON loading and saving;
- embedding NPZ loading and saving;
- cosine similarity;
- YuNet and SFace factory creation.

Application data lives outside the backend package:

```text
data/
|-- embeddings.npz
|-- metadata.json
`-- faces/<person>/*.jpg
```

### `download_models.py`

Optional setup script that downloads missing YuNet and SFace ONNX models from
the OpenCV model zoo:

```bash
python -m backend.download_models
```

It is not imported by the running backend.

## API endpoints

| Method | Endpoint                     | Purpose |
| ------ | ---------------------------- | ------- |
| `GET`  | `/api/health`                | Overall API, model, people, and robot summary |
| `GET`  | `/api/people`                | List enrolled identities |
| `POST` | `/api/recognize`             | Recognize one uploaded browser image |
| `POST` | `/api/enroll`                | Enroll one person from uploaded images |
| `GET`  | `/api/robot/status`          | Unitree camera configuration and capture state |
| `GET`  | `/api/robot/battery`         | Latest Unitree battery telemetry |
| `WS`   | `/api/robot/battery/ws`      | Push live Unitree battery telemetry |
| `GET`  | `/api/robot/control/status`  | Current locomotion-control service status |
| `GET`  | `/api/robot/services`        | List robot services and their on/off status |
| `POST` | `/api/robot/services/switch` | Turn an unprotected robot service on or off |
| `GET`  | `/api/robot/stereo/status`   | Stereo pipeline status, metrics, and detections |
| `WS`   | `/api/robot/stereo/ws`       | Push live stereo status, metrics, and detections |
| `POST` | `/api/robot/stereo/start`    | Start stereo capture and object detection |
| `POST` | `/api/robot/stereo/stop`     | Stop stereo capture and object detection |
| `POST` | `/api/robot/stereo/classes`  | Replace the YOLO-World object prompts |
| `GET`  | `/api/robot/stereo/stream/{view}` | Stream the detection or depth monitor |
| `GET`  | `/api/robot/mode`            | Current Unitree FSM mode |
| `WS`   | `/api/robot/mode/ws`         | Push current Unitree FSM mode |
| `POST` | `/api/robot/control`         | Send one bounded locomotion command |
| `POST` | `/api/robot/connect`         | Start the shared Unitree camera client |
| `GET`  | `/api/robot/snapshot`        | Return the newest Unitree JPEG |
| `GET`  | `/api/robot/stream`          | Return a live MJPEG stream |
| `POST` | `/api/robot/recognize`       | Recognize the newest Unitree frame |
| `GET`  | `/api/robot/speech/status`   | Report speech tool and busy status |
| `POST` | `/api/robot/speak`           | Convert English text and play it |
| `POST` | `/api/robot/led`             | Set the robot LED strip RGB color |

Interactive API docs are available while the backend is running:

```text
http://127.0.0.1:8000/docs
```

## Request limits

These limits are enforced in `main.py`:

- single uploaded image: `10 MB`
- maximum enrollment images per request: `30`
- maximum total enrollment payload: `100 MB`
- recognition threshold must be between `0.0` and `1.0`
- speech text length must be between `1` and `200` characters

## Startup behavior

On startup:

- `FaceService` loads the face models and database;
- `RobotBatteryService.start()` is called immediately;
- `RobotCameraService.start()` is called automatically only if
  `UNITREE_NETWORK_INTERFACE` is already configured.

That means webcam-only mode works without Unitree installed, while robot mode
can auto-connect when the interface is set before launch.

## Recommended run modes

### Webcam-only development

```bash
python backend/app.py
```

This is the easiest way to develop locally with Vite and browser webcam input.

### Robot mode with interface passed on the command line

```bash
python3 backend eth0
```

Use this when you want the backend launcher to set
`UNITREE_NETWORK_INTERFACE` for you.

### Apache reverse-proxy deployment on Raspberry Pi

If Apache proxies `/api/` to the backend, prefer binding only to localhost:

```bash
python3 backend eth0 --host 127.0.0.1 --port 8000
```

Or, if you already exported the interface yourself:

```bash
export UNITREE_NETWORK_INTERFACE=eth0
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

This keeps port `8000` off the LAN and lets Apache be the only public entry
point.

## CORS

The default allowed origins are:

- `http://localhost:5173`
- `http://127.0.0.1:5173`

Override them with a comma-separated environment variable:

```bash
export FR_CORS_ORIGINS=http://192.168.1.20:5173,http://10.0.0.50:5173
```

If you deploy the frontend behind Apache on the same host and use the same
origin, extra CORS configuration is usually unnecessary.

## Robot speech dependencies

Robot speech uses the Unitree SDK `AudioClient` directly. No local TTS model or
system audio package is required. Install the project requirements and ensure
`unitree_sdk2py` is available in the same Python environment.

Check support and send a manual speech test:

```bash
curl http://127.0.0.1:8000/api/robot/speech/status
curl -X POST http://127.0.0.1:8000/api/robot/speak \
  -H 'Content-Type: application/json' \
  -d '{"text":"Hello from Daikai Robot Hub"}'
```

## Robot states

### Camera service states

`RobotCameraService.status()` can report:

| State | Meaning |
| ----- | ------- |
| `not_configured` | `UNITREE_NETWORK_INTERFACE` is missing |
| `stopped` | Configured but capture has not started |
| `connecting` | DDS and camera client are starting |
| `connected` | Fresh JPEG frames are arriving |
| `reconnecting` | A temporary camera read failed and retry is in progress |
| `error` | SDK import or initialization failed |

## Quick verification

```bash
python -m py_compile backend/*.py
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:8000/api/people
curl http://127.0.0.1:8000/api/robot/status
curl http://127.0.0.1:8000/api/robot/speech/status
curl http://127.0.0.1:8000/api/robot/snapshot --output /tmp/robot.jpg
```

When troubleshooting imports, confirm the backend is using the intended Python
interpreter:

```bash
which python
python --version
python -c "import fastapi, cv2; from unitree_sdk2py.go2.video.video_client import VideoClient; print('OK')"
```


## Console IMU and Vision

The console subscribes to `/api/robot/imu/ws` (5 updates/second). The backend
reads `unitree_hg/LowState_` on `rt/lowstate`, configurable with
`UNITREE_IMU_TOPIC`, using `UNITREE_NETWORK_INTERFACE`. Readings include RPY
converted from radians to degrees, gyro in rad/s, acceleration in m/s²,
quaternion in W/X/Y/Z order, and temperature in °C. Stale or disconnected
readings are hidden by the console. `GET /api/robot/imu` returns the same payload.

Vision uses the existing stereo detection endpoints, with YOLO-World restricted
to `person`. It adds YuNet face detection and SFace recognition against
`data/embeddings.npz`. Names below the cosine similarity threshold are shown as
`Unknown`; the default threshold is 0.363 (`VISION_FACE_THRESHOLD`).
Face inference runs at the same interval as person detection. Vision reloads
the local database automatically when it changes. Restart Vision after changing
model settings.

Install the face models before using recognition:

```bash
python3 -m backend.download_models
```

The backend OpenCV build must provide `FaceDetectorYN` and `FaceRecognizerSF`
(OpenCV 4.8+ recommended for the 2023 YuNet model); keep the Jetson-specific
OpenCV installation used by stereo. NumPy is also required by both pipelines.
Override paths with `VISION_FACE_MODELS_DIR` and `VISION_FACE_DATABASE`.
Downloaded models are local assets excluded from Git. If face recognition
cannot initialize, person detection continues and the console shows the error.
The depth views and autonomous-walking depth consumers retain their existing
stereo processing.

## Firmware arm actions

The console's **Robot actions** box follows
`unitree_sdk2_python/my_script/r1_action.py`: it uses `G1ArmActionClient` with
the R1 firmware's `arm` service. `GET /api/robot/arm-actions` recursively reads
`GetActionList()` and returns every advertised ID/name. The UI creates a line-icon
button for each result, with **Refresh** to reload the list. It uses the firmware
IDs rather than the SDK's static G1 gesture map (`clamp` is displayed as Clap).

`POST /api/robot/arm-actions/execute` accepts `{"action_id": 7}`. The backend
checks current FSM **811**, reloads the firmware action list, validates the ID,
and calls `ExecuteAction`. It does not automatically change modes. Commands
share the locomotion lock and are rejected during polishing, teleoperation, or
autonomous walking. After dispatch, a 5-second cooldown prevents another action
or normal movement command; stop and stance/zero-torque commands remain
available. Acceptance is reported separately from completion because the arm
service has no completion event. Tests mock the robot clients and never send
physical action commands.


## Console Text to Speech and photo registration

The **Text to Speech** box calls the robot's native `AudioClient.TtsMaker`, as
in `reference_script/text_to_robot.py`. It has a 200-character message field,
the backend’s default voice, and volume 0–100 (UI default 70). Language support
is determined by firmware. `POST /api/robot/speak` accepts optional `speaker_id`
and `volume` along with `text`. Omitting options preserves the existing server
defaults. A success response indicates RPC acceptance, not completed playback.

In **Vision**, click **Register face** to open photo enrollment. Enter a name
and select 1–10 JPG, PNG or WebP photos (5 MB each, 25 MB total). Each accepted
photo must have exactly one detectable face. Results report accepted photos
and individual rejection reasons. Samples are appended to the existing
`VISION_FACE_DATABASE` archive; other people and previous samples are preserved.
Only embeddings are persisted by enrollment. Original uploaded photos are not
saved. `GET /api/vision/people` lists names and embedding counts;
`POST /api/vision/enroll` accepts multipart `name` and repeated `images` fields.

Enrollment runs in a worker thread with its own YuNet/SFace instances. Database
updates use a shared lock and atomic replacement; live Vision reloads the new
embeddings without restarting the stream. Install `python-multipart` from the
requirements file for uploads. Tests use temporary databases and mocked robot
clients, leaving real identities and robot audio untouched.


## Vision model startup cache

The stereo service retains its prepared YOLO-World model, text encoder and
predictor, and the live face-recognition models between stream start/stop
cycles. The first start still imports libraries and initializes model weights.
Later starts reuse them within the same backend process. Changes to weight file
mtime/size, device, or prompts invalidate the detector cache. This trades
retained RAM/VRAM for quicker restarts; restarting the backend clears the cache.
No inference resolution, thresholds, calibration or model weights were changed
by this optimization. `detection_model_cached` in stereo status reports whether
a detector has already been loaded.

### Optional RealSense D415 camera

Console and Autonomous Walk share a **Camera** selector: robot stereo cameras
(default) or **Intel RealSense D415 (USB)**. Stop all camera views and autonomous
walking before switching. The selection applies to both pages and resets to robot
stereo when the backend restarts.

Connect the D415 by USB to the machine running the backend, and install the
RealSense SDK Python binding (`pyrealsense2`) in that backend's Python environment.
Optionally set `R1_D415_SERIAL` to select one D415 when several are connected.
D415 capture uses 640×480 depth and 1280×720 native color at 30 FPS.
Set `R1_D415_COLOR_WIDTH=640` and `R1_D415_COLOR_HEIGHT=480` for lower bandwidth.
Console always copies native RGB before alignment; depth processing runs only
when a depth view or autonomous walking requests it. Depth aligns to color
and uses SDK metric points for the existing center-clearance and walking logic.
Robot stereo calibration and RTP streams are not used for this source.
YOLO and face-recognition dependencies are still required for Console Vision.
Validate camera mounting, forward alignment, and clearance measurements on the
robot before using autonomous walking with this source.

Vision runs YOLO and face recognition in one separate worker, with at most one
inference in progress and no queued camera frames. Preview and clearance updates
continue while inference runs; AI overlays expire after one second to avoid
showing stale boxes. Only subscribed views are JPEG-encoded (quality 92).
Console displays preview FPS and YOLO inference time for performance diagnosis.

The Console status line shows `native-rgb-v2` and the captured resolution for
D415. Restart the backend and reload the frontend after updating; this marker
confirms that the new RGB path is running. Holes in depth never mask the preview.

FSM WebSocket queries run in the thread pool so Unitree RPC timeouts cannot block
video delivery on the ASGI event loop. An FSM/ClientStub error still indicates
a robot communication problem; this change isolates its effect on the video.

Console alone opens the D415 color stream only: no USB depth stream, alignment,
point cloud, heatmap, or distance calculation. Opening Autonomous Walk's distance
monitor or starting a walk enables depth; removing the last depth consumer
returns the D415 to color-only capture. Reconfiguring the USB streams can cause
a brief preview pause. Robot stereo also skips depth matching for Console-only
use. The legacy generic start endpoint now starts the detection view only.

D415 startup checks SDK profile compatibility and falls back from the preferred
color size at 30 FPS to 640×480 at 30/15 FPS, then SDK-selected resolution/FPS.
Every attempt explicitly enables color only for Console; walking includes depth.
If no profile starts, the error lists attempted configurations instead of only
reporting "Couldn't resolve requests". The selected request is logged at startup;
the Console resolution/FPS line shows the running image size and processing rate.

The shared vision worker is paced at a maximum of 20 processed/output frames per
second, including AI submissions and JPEG encoding. Camera capture retains a
supported SDK hardware profile; a 20 FPS hardware profile is not requested.

Stop requests acknowledge cancellation without waiting for a walking/camera
thread to join. Walking waits are interruptible and send zero velocity when
cancelled; a pending Unitree RPC still has to finish or time out. WebSocket
status exposes `stop_requested` until the worker actually exits. Releasing a
walk's depth consumer leaves any visible monitor running and does not join it.

Frontend stop requests time out after eight seconds with an explicit warning
that the action may still be pending. Walking and distance-monitor buttons use
separate pending states, so a monitor request does not block Stop walking.
Distance streams detach while their stop request is pending. Camera stop
endpoints run directly on the event loop to avoid waiting behind streaming
thread-pool work; they only signal cancellation and return the current status.
