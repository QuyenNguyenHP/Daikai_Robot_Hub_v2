# Frontend Structure

The frontend is organized by responsibility so pages, camera behavior, and API
calls can be changed independently.

```text
src/
├── components/                 Reusable visual components
│   ├── AppHeader.jsx
│   ├── CameraStage.jsx
│   ├── RobotControlPanel.jsx
│   ├── RobotSpeechPanel.jsx
│   └── BatteryStatus.jsx
├── hooks/                      Reusable React state/lifecycle logic
│   ├── useBrowserCamera.js
│   └── useCameraSource.js
├── pages/                      Complete application screens
│   ├── EnrollmentPage.jsx
│   └── FirstPage.jsx
├── services/                   Backend and browser-facing operations
│   ├── api.js
│   ├── camera.js
│   └── detections.js
├── App.jsx                     Navigation and shared API state
├── main.jsx                    React entry point
└── styles.css                  Global visual system
```

## Responsibilities

### `components/`

Components receive data and callbacks through props. They should not own page
navigation or enrollment/recognition workflows. Put a component here when it is
reusable or represents a clear piece of UI.

### `pages/`

Each file represents one navigation screen. Pages combine components, hooks,
and services:

- `FirstPage` controls recognition polling, detection results, manual robot
  speech, and automatic recognized-name announcements.
- `EnrollmentPage` controls sample capture, previews, and submission.

### `hooks/`

- `useBrowserCamera` owns `getUserMedia`, media tracks, and browser-camera
  cleanup.
- `useCameraSource` provides one interface for selecting, starting, and stopping
  either the webcam or Unitree camera.

Camera lifecycle changes should normally be made here rather than repeated in
individual pages.

### `services/`

- `api.js` is the only module that knows backend URLs and HTTP endpoint details.
- `camera.js` captures browser video frames and waits for Unitree connection.
- `detections.js` adds image dimensions and smooths bounding boxes.

If a backend endpoint changes, update `services/api.js`; page components should
not contain raw `fetch` calls.

### `App.jsx`

`App` only owns state shared across screens: current page, API health, and
backend connection errors. It does not contain camera or recognition logic.

## Development

Use Node.js 22 (Node.js 20.19 or newer is also supported). With `nvm`:

```bash
cd frontend
nvm install
nvm use
node --version
```

Then install and start the frontend:

```bash
npm install
npm run dev
```

Set a remote backend before starting Vite when required:

```bash
export VITE_API_URL=http://BACKEND_IP:8000
npm run dev
```

Verify a production build:

```bash
npm run build
```

## Adding a page

1. Create `src/pages/NewPage.jsx`.
2. Add its navigation item to `components/AppHeader.jsx`.
3. Render it conditionally from `App.jsx`.

For a larger application, React Router can replace the current small
state-based navigation without changing the existing page components.


## Robot Monitor / HUD theme

The default **Robot Monitor** page adapts the root `index.html` HUD reference
using Inter, JetBrains Mono, cyan accents, translucent navy panels, and the same
theme variables used by Console, Teleoperation, Autonomous Walk and System
Services. The original reference file is preserved.

`MonitorPage` is loaded separately so Three.js is not bundled into the control
pages. `RobotModel` loads an optimized indexed GLB through Vite's asset pipeline.
The original root `R1_full_robot.stl` is preserved, but is not downloaded by the
web viewer. The GLB is 1,760,452 bytes / 79,997 triangles, compared with the
31,407,184-byte / 628,142-triangle STL (94.4% fewer bytes, 87.3% fewer triangles).
Geometry is fetched and decoded once per page session; viewer instances clone
it so navigation cleanup does not invalidate the cache. Rendering is capped at
30 fps, runs only when controls or telemetry change, and pauses when the tab is
hidden or the model is outside the viewport. Compass ticks use one instanced
draw call and device pixel ratio is capped at 1.5. Drag to orbit,
scroll/pinch to zoom, use **Reset view**, or toggle **Wireframe**. WebGL is
required for 3D; the telemetry panels work independently.

The HUD subscribes to the existing battery and IMU WebSockets. It shows actual
cell voltages from BMS, body orientation from Unitree W/X/Y/Z quaternion data,
angular velocity, acceleration and temperature. Battery charts keep the latest
60 seconds while the page is open, each with its own labelled units and scale.
No simulated readings are generated. Closed/stalled WebSockets and stale DDS
readings display offline values; the model holds the last attitude dimmed.

The STL is a single rigid mesh. Body attitude follows IMU, while individual
joints are not animated. This page sends no robot movement commands.


To regenerate the model after replacing the source STL:

```bash
python3 -m pip install trimesh==5.2.2 fast-simplification==0.2.0
python3 tools/optimize_robot_model.py
```

These are build tools, not backend runtime dependencies. The asset metadata is
in `src/assets/r1-monitor.json`. Check the actual GLB loader and cache without
WebGL using `node frontend/scripts/check-robot-model.mjs` from the repository
root. This check does not measure browser frame rate.
