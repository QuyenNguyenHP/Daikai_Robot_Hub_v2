# Technology Stack

This document lists the languages, frameworks, libraries, tools, protocols, and deployment components used by Daikai Robot Hub v2.

## 1. Frontend

- **React.js** — builds the user interface with reusable components and React Hooks.
- **React DOM** — renders the React application in the browser.
- **JavaScript (ES Modules)** — the main frontend programming language.
- **JSX** — defines component markup inside JavaScript files.
- **HTML5** — provides the application entry page and document structure.
- **CSS3** — provides layout, styling, responsive behavior, and visual effects.
- **Vite** — provides the development server and production build process.
- **Node.js 20 or newer** — runs Vite and the frontend build tools. Node.js is not used as the application backend.
- **npm 10 or newer** — installs and manages frontend packages.

### Browser APIs

- **Fetch API** — sends HTTP requests to the FastAPI backend.
- **FormData** — uploads enrollment and recognition images as multipart form data.
- **MediaDevices / `getUserMedia()`** — accesses a webcam connected to the browser device.
- **Canvas API** — captures webcam frames and converts them to JPEG blobs.
- **Blob, File, and URL APIs** — handle captured images and API responses.
- **Timers** — periodically refresh robot status, battery data, and recognition results.

The direct frontend packages are declared in [`frontend/package.json`](frontend/package.json).

## 2. Backend

- **Python** — FastAPI and robot integration language. The Jetson GPU deployment profile documented below uses **Python 3.8.10** because NVIDIA's JetPack 5.1.1 PyTorch wheel targets CPython 3.8.
- **FastAPI** — defines the REST API and application lifecycle.
- **Uvicorn** — runs the FastAPI application as an ASGI server.
- **Pydantic** — validates structured API request bodies.
- **FastAPI CORS middleware** — allows approved frontend origins to access the API.
- **python-multipart** — parses file uploads and multipart form submissions.
- **Requests** — calls external HTTP services, including the local Voice AI server.
- **Python threading** — runs robot camera, battery, speech, and control operations safely in the background.

The direct Python packages are declared in [`requirements.txt`](requirements.txt). The API routes are defined in [`backend/main.py`](backend/main.py).

## 3. Face Detection and Recognition

- **OpenCV Contrib Python** — supplies image processing and the YuNet/SFace APIs.
- **OpenCV YuNet** — detects faces in uploaded or camera images.
- **OpenCV SFace** — aligns faces and generates recognition embeddings.
- **ONNX** — stores the pretrained YuNet and SFace models.
- **NumPy** — processes images and embeddings and calculates similarity scores.
- **Cosine similarity** — compares a detected face embedding with enrolled embeddings.
- **NPZ** — stores compressed face embeddings in `data/embeddings.npz`.
- **JSON** — stores enrollment metadata in `data/metadata.json`.
- **JPEG** — stores enrolled face crops and transports camera snapshots and frames.

The main recognition implementation is in [`backend/face_service.py`](backend/face_service.py), with shared model and data utilities in [`backend/common.py`](backend/common.py).

## 4. Unitree R1 Robot Integration

- **Unitree SDK2 Python (`unitree_sdk2py`)** — communicates with the Unitree R1 robot.
- **Cyclone DDS / DDS** — provides the underlying real-time communication layer.
- **Unitree `VideoClient`** — receives images from the robot camera.
- **Unitree `LocoClient`** — sends movement commands and queries the locomotion FSM mode.
- **Unitree `AudioClient`** — streams PCM audio to the robot speaker.
- **Unitree DDS BMS messages** — provide live battery telemetry.

The robot services use environment variables including:

- `UNITREE_NETWORK_INTERFACE` — selects the network interface connected to the robot.
- `UNITREE_BATTERY_TOPIC` — optionally overrides the default DDS battery topic.

The integration is implemented in:

- [`backend/robot_camera.py`](backend/robot_camera.py)
- [`backend/robot_control.py`](backend/robot_control.py)
- [`backend/robot_battery.py`](backend/robot_battery.py)
- [`backend/robot_audio.py`](backend/robot_audio.py)

### Robot speaker streaming

`RobotAudioService.play_wav()` accepts WAV audio from the local Voice AI server,
converts it to 16 kHz, mono, signed 16-bit PCM, and sends timed chunks through
`AudioClient.PlayStream()`. It finishes every playback session with
`AudioClient.PlayStop()`.

The browser Voice AI panel has this pipeline:

```text
Browser microphone (MediaRecorder)
  -> FastAPI /api/robot/voice-chat
  -> Voice AI server /v1/voice/chat
  -> Whisper STT -> Ollama chat -> Kokoro WAV
  -> FastAPI WAV conversion to R1 PCM
  -> Unitree AudioClient.PlayStream
  -> R1 speaker
```

The FastAPI backend reads `VOICE_AI_SERVER_URL`, optional
`VOICE_AI_API_KEY`, and `VOICE_AI_TIMEOUT_SECONDS`. The key is never sent to
the browser.

The Unitree SDK is an optional external dependency and is loaded only when robot functionality is used. It is not listed in the project's main `requirements.txt` because it has a separate installation process.

## 5. Stereo Object Distance and YOLO-World

The Object Distance page combines the R1 stereo streams with YOLO-World object
detection. The implementation is in
[`backend/robot_stereo_detection.py`](backend/robot_stereo_detection.py), and
its camera/calibration helpers and assets are in
[`backend/r1_yolo_world_stereo/`](backend/r1_yolo_world_stereo/).

### Runtime pipeline

```text
R1 stereo service
  -> RTP/H.264 UDP streams: left 5002, right 5003
  -> GStreamer/OpenCV decoder threads
  -> synchronized left/right pair
  -> calibration rectification
  -> OpenCV StereoSGBM disparity
  -> 3D reprojection using calibration Q matrix
  -> YOLO-World GPU inference on the rectified left image
  -> median depth from the central portion of each detection
  -> annotated detection image + disparity preview as MJPEG
  -> React Object Distance page
```

- **YOLO-World** — detects the configured English object prompts, such as
  `person`, `chair`, `bottle`, and `door`.
- **OpenAI CLIP ViT-B/32** — encodes custom YOLO-World object prompts.
- **OpenCV** — rectifies stereo frames, computes SGBM disparity, reprojects
  points to metric 3D space, annotates frames, and encodes MJPEG images.
- **NumPy** — performs depth sampling, filtering, and robust median distance
  calculation.
- **CUDA/PyTorch** — runs YOLO-World inference on the Jetson GPU. StereoSGBM
  depth remains a CPU operation.
- **GStreamer** — decodes R1 RTP/H.264 streams when OpenCV lacks GStreamer
  support.

The detector runs CPU depth calculation concurrently with GPU YOLO inference.
It reports device name, frame rate, YOLO latency, stereo latency, pair delta,
and detected distances through REST and WebSocket status APIs.

### Required model and calibration assets

These files are deployed outside normal Python package installation:

| Asset | Purpose |
| --- | --- |
| `backend/r1_yolo_world_stereo/yolov8s-worldv2.pt` | YOLO-World detection model |
| `backend/r1_yolo_world_stereo/r1_stereo_calibration.npz` | Camera intrinsics, distortion, rotation, translation, and Q matrix |
| `backend/r1_yolo_world_stereo/weights/clip/ViT-B-32.pt` | Cached CLIP text encoder for offline custom prompts |

`ViT-B-32.pt` is about 338 MB and is intentionally excluded from Git. Copy it
to the path above after deployment so the server does not download it again.

### Jetson Orin Nano GPU deployment profile — verified

The following combination was tested successfully for YOLO-World GPU inference:

| Component | Version / value |
| --- | --- |
| Board | NVIDIA Jetson Orin Nano Developer Kit |
| JetPack / L4T | JetPack 5.1.1 / R35.3.1 |
| CUDA | 11.4.315 |
| cuDNN | 8.6.0 |
| Python | 3.8.10 |
| NVIDIA PyTorch | `2.0.0+nv23.05` |
| torchvision | Source-built `0.15.1` with CUDA operators |
| CUDA architecture | `8.7` for Orin |
| Ultralytics | `8.3.0` |
| OpenCV | `opencv-python-headless==4.10.0.84` |

> **Deployment requirement — GPU depends on the backend environment.** Installing
> NVIDIA PyTorch in one virtual environment does not make CUDA available to a
> backend started with another Python interpreter. Every terminal, service, and
> restart that runs FastAPI must activate or directly use the same Python 3.8
> environment containing `torch==2.0.0+nv23.05`, the CUDA-enabled torchvision
> build, Ultralytics, and OpenCV headless. Confirm this before starting the
> backend with `which python` and `python -c "import torch; print(torch.cuda.is_available())"`.
> The expected result is `True`.

Do **not** use the generic desktop `torch 2.13.0+cu130` wheel on JetPack
5.1.1. It targets CUDA 13.0 while this Jetson driver supports CUDA 11.4, so
`torch.cuda.is_available()` returns `False`.

#### Installation sequence

Create a separate Python 3.8 virtual environment first. Keep the previous
Python 3.10 environment as a rollback backup.

```bash
cd /home/unitree/Daikai_Robot_Hub_v2
python3.8 -m venv .venv-gpu
source .venv-gpu/bin/activate

python -m pip install --upgrade pip
python -m pip install 'numpy==1.24.4' 'setuptools<70' wheel ninja
python -m pip install \
  'https://developer.download.nvidia.com/compute/redist/jp/v511/pytorch/torch-2.0.0+nv23.05-cp38-cp38-linux_aarch64.whl'
```

Build torchvision 0.15.1 from source because its CUDA NMS operator must match
the installed NVIDIA PyTorch wheel:

```bash
cd /home/unitree/jetson-build/torchvision-v0.15.1
export CUDA_HOME=/usr/local/cuda
export TORCH_CUDA_ARCH_LIST=8.7
export FORCE_CUDA=1
export MAX_JOBS=2
python -m pip install --no-build-isolation --no-deps .
```

Install the remaining runtime dependencies without replacing `torch` or the
source-built `torchvision`:

```bash
python -m pip install --no-deps 'ultralytics==8.3.0'
python -m pip install \
  'opencv-python-headless==4.10.0.84' pillow requests \
  matplotlib pyyaml scipy pandas seaborn tqdm psutil py-cpuinfo \
  ultralytics-thop ftfy regex \
  fastapi 'uvicorn[standard]' pyzmq eval-type-backport
python -m pip install 'git+https://github.com/openai/CLIP.git'
```

`eval-type-backport` lets FastAPI/Pydantic on Python 3.8 evaluate the backend's
newer annotations such as `dict[str, object]` and `str | None` without changing
the API implementation.

Ultralytics 8.3.0 uses OpenAI CLIP directly and does not provide
`ultralytics.nn.text_model`. The Object Distance backend therefore supports
both its legacy CLIP API and the newer Ultralytics text-model API. A misleading
"Ultralytics is not installed" error can otherwise be caused by importing the
newer-only `text_model` module in an installed 8.3.0 environment.

Use OpenCV **headless** on Jetson. The GUI build may fail after importing torch
with this error:

```text
libGLdispatch.so.0: cannot allocate memory in static TLS block
```

Headless OpenCV keeps all required stereo functions while removing the unused
OpenGL GUI dependency. Install Unitree SDK2 from the local Unitree source into
the same virtual environment:

```bash
python -m pip install -e /absolute/path/to/unitree_sdk2_python
```

#### Verification before starting the robot backend

```bash
python - <<'PY'
import cv2
import torch
import torchvision
from ultralytics import YOLOWorld

assert torch.cuda.is_available(), 'CUDA is unavailable'
boxes = torch.tensor([[0., 0., 10., 10.], [1., 1., 9., 9.]], device='cuda:0')
scores = torch.tensor([0.9, 0.8], device='cuda:0')
assert torchvision.ops.nms(boxes, scores, 0.5).cpu().tolist() == [0]
print('GPU:', torch.cuda.get_device_name(0))
print('OpenCV:', cv2.__version__)
print('YOLO-World import passed')
PY
```

Then start the backend from the same activated environment:

```bash
cd /home/unitree/Daikai_Robot_Hub_v2
R1_YOLO_DEVICE=cuda:0 python -m backend eth0
```

Replace `eth0` with the actual R1-facing network interface. The ordinary video
viewer and Object Distance both use the right stereo stream on UDP 5003, so the
application prevents them from running concurrently.

For a `systemd` deployment, do not use `/usr/bin/python3` or an old Python 3.10
environment in `ExecStart`. Point it explicitly to the GPU environment, for
example:

```ini
ExecStart=/home/unitree/Daikai_Robot_Hub_v2/.venv-gpu/bin/python -m backend eth0
Environment=R1_YOLO_DEVICE=cuda:0
```

Use the actual environment name if it is `.venv-gpu-test`. After changing a
unit file, run `sudo systemctl daemon-reload` and restart that service.

## 6. Speech and Audio Tools

Robot speech requires one text-to-speech engine:

- **pico2wave** (preferred), or
- **espeak-ng**, or
- **espeak**.

It also requires one audio conversion tool:

- **FFmpeg**, or
- **SoX**.

The selected tools generate and normalize speech as 16 kHz, mono, 16-bit PCM WAV audio before it is streamed through the Unitree `AudioClient`.

## 7. Frontend–Backend Communication

- **HTTP REST API** — handles health checks, face enrollment, recognition, and robot operations.
- **JSON** — transfers structured requests and responses.
- **`multipart/form-data`** — uploads one or more images.
- **JPEG snapshots** — return individual robot-camera frames.
- **MJPEG (`multipart/x-mixed-replace`)** — streams live robot-camera frames.
- **CORS** — supports frontend and backend development on different origins.
- **WebSockets** — publish battery, robot mode, and stereo-detection status
  updates to the frontend.

The Object Distance API includes `/api/robot/stereo/status`,
`/api/robot/stereo/start`, `/api/robot/stereo/stop`,
`/api/robot/stereo/classes`, `/api/robot/stereo/ws`, and live MJPEG streams.

## 8. Deployment and Operating Environment

- **Apache2** — serves the production frontend build.
- **Apache `proxy` and `proxy_http` modules** — reverse-proxy `/api/*` requests to FastAPI/Uvicorn.
- **Apache `rewrite` module** — supports frontend client-side paths.
- **Apache `headers` module** — manages required HTTP headers.
- **systemd** — runs the backend automatically as a Linux service.
- **Raspberry Pi OS, Debian, or Ubuntu Linux** — documented deployment environments.
- **Python `venv` and pip** — isolate and install Python packages.

Deployment instructions are available in [`APACHE2_LAN_SETUP_vi.md`](APACHE2_LAN_SETUP_vi.md).

## 9. Source and Data Formats

| Format | Purpose |
| --- | --- |
| `.py` | Backend and robot scripts |
| `.js` | Frontend services, hooks, and Vite configuration |
| `.jsx` | React components and pages |
| `.css` | Application styling |
| `.html` | Frontend entry document |
| `.json` | npm metadata and application metadata |
| `.npz` | Compressed NumPy face embeddings |
| `.onnx` | Pretrained face detection and recognition models |
| `.pt` | YOLO-World and CLIP PyTorch model weights |
| `.jpg` / `.png` | Face samples and frontend image assets |
| `.md` | Project documentation |

## 10. Stack Summary

```text
Frontend:   React + JavaScript/JSX + HTML + CSS + Vite
Build:      Node.js + npm
Backend:    Python + FastAPI + Uvicorn + Pydantic
Vision/AI:  OpenCV + YOLO-World + CLIP + PyTorch CUDA + NumPy
Robot:      Unitree SDK2 Python + Cyclone DDS
Audio:      Unitree PlayStream + Voice AI server + pico2wave/espeak + FFmpeg/SoX
Deployment: Apache2 + systemd + Linux + Jetson Orin Nano / JetPack
```

## 11. Technologies Not Currently Used

Based on the current source code and dependency manifests, the project does not use:

- Node.js or Express as the backend
- TypeScript
- Next.js
- React Router
- Redux or another global state-management library
- SQL or NoSQL databases
- Docker or Docker Compose
- A cloud hosting SDK
