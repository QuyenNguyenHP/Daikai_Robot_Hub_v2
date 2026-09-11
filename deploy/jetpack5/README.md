# Orin Nano / JetPack 5.1.1 / one Python 3.8 environment

Target: L4T R35.3.1, aarch64, CUDA 11.4, Python 3.8.10. This profile keeps
JetPack unchanged and uses NVIDIA's prebuilt PyTorch. Torchvision is built
locally because its CUDA NMS extension must match that PyTorch installation.
These steps require internet access and have not been hardware-tested here.
Do not use this profile for JetPack 6 or a desktop RTX PC.

The backend annotation changes and legacy CLIP loader must be deployed from
this working tree before migration. Do not assume they are already on GitHub.
If you received `jetpack5-python38-update.tar.gz`, back up local code edits,
then extract it into the v2 repository (it updates code, not model weights):

```bash
cd ~/Daikai_Robot_Hub_v2
tar -xzf ~/Downloads/jetpack5-python38-update.tar.gz
```

Adjust the archive path to wherever you copied it.
The React frontend stays unchanged. The existing XR teleoperation launcher
still uses its external `tv` Conda environment; this guide unifies the web
backend and YOLO environment, not that separate XR application.

## 1. Save the current environment and install system build tools

Stop the backend first. In your existing activated Python 3.10 environment:

```bash
python -m pip freeze > ~/robot-python310-backup.txt
deactivate
sudo apt-get update
sudo apt-get install -y python3.8-venv python3.8-dev libopenblas-dev \
  build-essential git libjpeg-dev zlib1g-dev \
  gstreamer1.0-tools gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
  gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly gstreamer1.0-libav
/usr/local/cuda/bin/nvcc --version
```

If nvcc is missing, install the CUDA toolkit matching the existing JetPack
through NVIDIA's JetPack packages before building torchvision. Do not install
a desktop NVIDIA driver. Keep the existing Unitree SDK source and DDS library
configuration; a pip freeze does not back up those native libraries.

## 2. Recreate the environment at the same path

Only after the updated code is available locally:

```bash
cd ~/Daikai_Robot_Hub
# Refuse to overwrite an earlier backup.
test ! -e .venv-python310-backup && mv .venv .venv-python310-backup
# If the preceding command failed, stop and resolve the backup path first.
python3.8 -m venv .venv
source .venv/bin/activate
python -m pip install 'pip==24.3.1' 'setuptools==69.5.1' 'wheel==0.44.0'
python -m pip install 'numpy==1.24.4'
python -m pip install \
  'https://developer.download.nvidia.com/compute/redist/jp/v511/pytorch/torch-2.0.0+nv23.05-cp38-cp38-linux_aarch64.whl'
python -c "import torch; assert torch.cuda.is_available(); print(torch.cuda.get_device_name(0))"
```

Stop on any error. Do not continue if CUDA is unavailable.
The old environment is retained for rollback; do not run it at its renamed
path because venv scripts contain absolute paths. Restore its original name
before using it again.

## 3. Build torchvision and install the application profile

Use the actual v2 repository directory below. Build in a new temporary directory
so an existing source checkout is never overwritten. MAX_JOBS=2 limits build
memory use; reduce to 1 if necessary. Compilation can take a while.

```bash
cd ~/Daikai_Robot_Hub_v2
export PIP_CONSTRAINT="$PWD/deploy/jetpack5/constraints.txt"
python -m pip install 'pillow==10.4.0' 'requests==2.32.3'
vision_build_dir=$(mktemp -d /tmp/robot-torchvision.XXXXXX)
git clone --depth 1 --branch v0.15.1 https://github.com/pytorch/vision.git "$vision_build_dir"
cd "$vision_build_dir"
CUDA_HOME=/usr/local/cuda FORCE_CUDA=1 TORCH_CUDA_ARCH_LIST=8.7 \
  BUILD_VERSION=0.15.1 MAX_JOBS=2 \
  python -m pip install --no-build-isolation --no-deps .
cd ~/Daikai_Robot_Hub_v2
python -m pip install -r deploy/jetpack5/requirements.txt
python -m pip check
```

This profile uses pip OpenCV. The stereo capture code uses `gst-launch-1.0`
when that OpenCV build lacks GStreamer, so the system GStreamer decoder
packages above are required. No CUDA-enabled OpenCV build is required.
Keep the constraints active when adding packages so pip cannot silently
replace NVIDIA torch or the locally compiled torchvision.

## 4. Restore robot dependencies and model assets

Install the same Unitree SDK revision used by the old deployment into the new
environment, using your existing SDK checkout and CycloneDDS setup. For example,
after substituting the real source path:

```bash
python -m pip install -e /absolute/path/to/unitree_sdk2_python
python -c "from unitree_sdk2py.core.channel import ChannelFactoryInitialize; print('Unitree import OK')"
python -m pip check
```

Do not blindly reinstall the Python 3.10 freeze file: it includes the incompatible
CUDA 13 torch build. If a Unitree dependency conflicts with the profile, resolve
that specific dependency before starting robot control.

Ensure these files exist under `backend/r1_yolo_world_stereo/`:

- `yolov8s-worldv2.pt`
- `r1_stereo_calibration.npz` for the actual camera pair
- `weights/clip/ViT-B-32.pt` (excluded from Git; copy from the old deployment)

Without the CLIP cache, the first custom-prompt test downloads it. Run the test
online before taking the Jetson offline.

## 5. Verify and start

```bash
cd ~/Daikai_Robot_Hub_v2
python deploy/jetpack5/check_gpu.py
python -m unittest discover -s tests -p 'test_python38_deployment.py'
R1_YOLO_DEVICE=cuda:0 python -m backend eth0
```

Replace `eth0` with the robot-facing interface actually used by your deployment.
The GPU check verifies an actual CUDA NMS operation, YOLO-World custom prompts,
inference and FastAPI schema creation; it does not move or connect to the robot.
Then use the frontend to confirm battery/services, start stereo detection and
check GPU name, live frames and distance readings. No Jetson FPS is promised.

Your normal activation remains:

```bash
cd ~/Daikai_Robot_Hub
source .venv/bin/activate
cd ~/Daikai_Robot_Hub_v2
```

## Rollback

Stop the backend and deactivate the new environment. From `~/Daikai_Robot_Hub`,
move the new `.venv` to an unused backup name, then rename
`.venv-python310-backup` back to `.venv`. This preserves both environments and
restores the old absolute paths. The old CUDA 13 mismatch will still exist.

## Sources

- NVIDIA JetPack 5.1.1: https://developer.nvidia.com/embedded/jetpack-sdk-511
- NVIDIA PyTorch installation: https://docs.nvidia.com/deeplearning/frameworks/install-pytorch-jetson-platform/index.html
- Ultralytics 8.3.0 dependencies: https://github.com/ultralytics/ultralytics/blob/v8.3.0/pyproject.toml
- Ultralytics legacy CLIP API: https://github.com/ultralytics/ultralytics/blob/v8.3.0/ultralytics/nn/tasks.py
- Torchvision build source: https://github.com/pytorch/vision/tree/v0.15.1
