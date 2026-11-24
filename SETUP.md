# Simple Setup Guide

Use these steps after cloning Daikai Robot Hub from GitHub.

## 1. Clone the project

```bash
git clone <repository-url>
cd Daikai_Robot_Hub
```

Replace `<repository-url>` with this repository's GitHub URL.

## 2. Install Node.js 22

The frontend requires Node.js 22 and npm 10 or newer. Install them with `nvm`:

```bash
curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.6/install.sh -o /tmp/nvm-install.sh && bash /tmp/nvm-install.sh
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"
nvm install 22
nvm use 22
nvm alias default 22
```

Verify the versions:

```bash
node --version
npm --version
```

Node should report `v22.x.x` and npm should report `10.x.x` or newer.

### Unitree Ubuntu: certificate error or ROS selection prompt

If curl reports `SSL certificate problem: certificate is not yet valid`, check
the Unitree computer's clock first. A clock set too far in the past can cause
this error:

```bash
date -Is
timedatectl status
sudo timedatectl set-ntp true
```

With internet access, allow time synchronization to complete, then run
`timedatectl status` again and check that the date and time are correct. If
automatic synchronization is unavailable, set the current time manually using
the computer's configured timezone:

```bash
sudo timedatectl set-ntp false
sudo timedatectl set-time 'YYYY-MM-DD HH:MM:SS'
```

Replace the placeholder with the actual current date and time, then retry the
installation commands above. Do not bypass certificate verification with
`curl -k`. If the clock is correct and the error persists, check the network's
HTTPS proxy and certificate configuration.

The `ros:foxy(1) noetic(2) ?` prompt comes from the computer's shell startup
configuration when `source ~/.bashrc` runs. It is separate from the failed
download and does not mean nvm was installed. If you are currently at this prompt,
press **Ctrl+C** to return to the shell. The commands above load nvm directly,
without rerunning `.bashrc` or selecting a ROS distribution.

## 3. Set up the backend

For Orin Nano / JetPack 5.1.1 stereo detection, also follow the JetPack 5
section below. The generic backend requirements alone do not install the GPU
inference stack.

From the project root, create a Python virtual environment and install the
dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If Ubuntu reports that `ensurepip` is unavailable, install the venv package
matching your Python version, then repeat the commands above. For the Unitree
computer running Python 3.8:

```bash
sudo apt update
sudo apt install -y python3.8-venv
```

After activation, the terminal prompt should show `(.venv)`. Run the remaining
Python installation and startup commands in that environment, without `sudo`.

On Python 3.8, if startup reports
`Unable to evaluate type annotation 'dict[str, object]'`, install the typing
compatibility package in the active environment:

```bash
python -m pip install eval-type-backport
```

For local development without a robot connection, start the backend with:

```bash
python backend/app.py
```

The API will run at `http://localhost:8000`.

### Install Unitree SDK2 Python for a robot connection

Unitree SDK2 Python is required to connect to the robot. With the project's
`(.venv)` still active, install it from the official repository:

```bash
cd ~
git clone https://github.com/unitreerobotics/unitree_sdk2_python.git
cd unitree_sdk2_python
python -m pip install -e .
```

If you already cloned the SDK, use its existing directory and run the pip
command there.

#### Fix: `Could not locate cyclonedds`

If SDK installation fails with
`Could not locate cyclonedds. Try to set CYCLONEDDS_HOME or CMAKE_PREFIX_PATH`,
build the native Cyclone DDS library first, following the
[Unitree SDK2 Python FAQ](https://github.com/unitreerobotics/unitree_sdk2_python#faq).
Keep the project's `(.venv)` active and run each step below. Stop if a command
fails and resolve that error before continuing.

Install the build tools:

```bash
sudo apt update
sudo apt install -y build-essential cmake git
```

Download and build Cyclone DDS:

```bash
cd ~
git clone --branch releases/0.10.x https://github.com/eclipse-cyclonedds/cyclonedds.git
cd ~/cyclonedds
cmake -S . -B build -DCMAKE_INSTALL_PREFIX="$HOME/cyclonedds/install"
cmake --build build --target install -j2
```

If `~/cyclonedds` already contains a checkout of `releases/0.10.x`, skip the
clone command and use that directory.

Point the Python build at the installed library and retry SDK installation:

```bash
export CYCLONEDDS_HOME="$HOME/cyclonedds/install"
export CMAKE_PREFIX_PATH="$CYCLONEDDS_HOME${CMAKE_PREFIX_PATH:+:$CMAKE_PREFIX_PATH}"
export LD_LIBRARY_PATH="$CYCLONEDDS_HOME/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
cd ~/unitree_sdk2_python
python -m pip install -e .
```

The export applies to the current terminal. If you retry installation in a new
terminal, activate the project's `.venv` and repeat the export first.
`CYCLONEDDS_HOME` and `CMAKE_PREFIX_PATH` locate the native library during
builds; `LD_LIBRARY_PATH` makes its shared libraries discoverable at runtime.

#### Start with a robot connection

After SDK installation succeeds, return to the project directory (adjust the
path if you cloned it elsewhere):

```bash
cd ~/Daikai_Robot_Hub_v2
```

Start the backend with the network interface connected to the robot:

```bash
python backend <robot-network-interface>
```

For example:

```bash
python backend eth10
```

Replace `eth10` with your actual robot network interface. Use `ip -br link` to
list the available interfaces. SDK2 is optional for local development using
`python backend/app.py`.

## 4. Set up the frontend

Open a second terminal and run:

```bash
cd Daikai_Robot_Hub/frontend
nvm use
npm install
npm run dev
```

Open `http://localhost:5173` in a browser.

## Start the project again later

Backend terminal:

```bash
cd Daikai_Robot_Hub
source .venv/bin/activate
python backend/app.py
```

Frontend terminal:

```bash
cd Daikai_Robot_Hub/frontend
nvm use
npm run dev
```

## Common Node.js problem

If `node --version` still reports Node 18, load `nvm` and select Node 22:

```bash
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"
nvm use 22
hash -r
node --version
```

## Jetson Orin Nano: stereo trên JetPack 5.1.1 / Python 3.8

Phần này dành cho **Orin Nano, L4T R35.3.1, CUDA 11.4, Python 3.8**.
Không áp dụng nguyên xi cho Jetson Nano đời cũ hoặc JetPack 6. Tham khảo
[profile triển khai đầy đủ](deploy/jetpack5/README.md), đặc biệt nếu chuyển từ
môi trường Python 3.10 cũ. Không thay thế Python hệ thống.

Các lệnh dưới đây dùng duy nhất môi trường
`~/Daikai_Robot_Hub_v2/.venv`. Nếu môi trường hiện tại nằm ở đường dẫn khác,
hãy dùng đúng môi trường đó xuyên suốt; không trộn SDK và torch ở hai venv.
Dừng backend trước khi cài, chạy từng bước và dừng khi gặp lỗi.

### Mục đích các thành phần

| Thành phần | Vì sao cần |
| --- | --- |
| `python3.8-venv` | Tạo môi trường riêng có pip; sửa lỗi thiếu `ensurepip`. |
| `python3.8-dev`, `build-essential` | Header Python và compiler để build extension native. |
| `wheel`, `setuptools`, `pip` | Công cụ đóng gói và build; thiếu `wheel` gây `invalid command 'bdist_wheel'` khi dùng `--no-build-isolation`. |
| `ninja-build` | Backend build giúp giới hạn tác vụ bằng `MAX_JOBS`, giảm nguy cơ hết RAM khi build torchvision. |
| CUDA toolkit / `nvcc` | Biên dịch extension CUDA của torchvision; torch nhận GPU chưa chứng minh có compiler CUDA. |
| NVIDIA PyTorch | Chạy inference trên GPU với binary phù hợp JetPack; không thay bằng `pip install torch` thông thường. |
| torchvision build từ source | Cung cấp toán tử CUDA như NMS tương thích với NVIDIA torch đang dùng. |
| NumPy 1.24.4 và constraints | Giữ bộ phiên bản phù hợp profile Python 3.8, tránh pip thay torch/torchvision bằng binary khác. |
| JPEG, zlib, OpenBLAS | Thư viện native hỗ trợ ảnh và tính toán cho bộ dependency. |
| GStreamer và plugins | Nhận/giải mã video stereo; ứng dụng dùng `gst-launch-1.0` khi pip OpenCV không có GStreamer. |
| Ultralytics và OpenAI CLIP | Chạy YOLO-World và mã hóa nhãn văn bản tùy chỉnh. |
| Unitree SDK2 + Cyclone DDS | Giao tiếp với robot; đây là lớp riêng với xử lý GPU. |

### 1. Công cụ hệ thống và công cụ build Python

```bash
sudo apt update
sudo apt install -y python3.8-venv python3.8-dev libopenblas-dev \
  build-essential git cmake ninja-build libjpeg-dev zlib1g-dev \
  gstreamer1.0-tools gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
  gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly gstreamer1.0-libav

cd ~/Daikai_Robot_Hub_v2
# Chỉ cần tạo nếu chưa có môi trường tại đây:
# python3.8 -m venv .venv
source .venv/bin/activate
python --version
python -m pip install 'pip==24.3.1' 'setuptools==69.5.1' 'wheel==0.44.0'
/usr/local/cuda/bin/nvcc --version
```

Python phải là 3.8. Nếu thiếu `nvcc`, dừng và cài CUDA toolkit phù hợp
JetPack đang có theo tài liệu NVIDIA; không cài driver NVIDIA desktop.

### 2. Cài NVIDIA torch và kiểm tra GPU

```bash
cd ~/Daikai_Robot_Hub_v2
export PIP_CONSTRAINT="$PWD/deploy/jetpack5/constraints.txt"
python -m pip install 'numpy==1.24.4'
python -m pip install 'https://developer.download.nvidia.com/compute/redist/jp/v511/pytorch/torch-2.0.0+nv23.05-cp38-cp38-linux_aarch64.whl'
python -c "import torch; print(torch.__version__); assert torch.cuda.is_available(); print(torch.cuda.get_device_name(0))"
```

Nếu đã có `2.0.0+nv23.05` và CUDA hoạt động, không cần cài lại torch.
Lỗi `No module named 'torch'` nghĩa là môi trường chạy backend chưa có torch;
kiểm tra `which python` và `echo "$VIRTUAL_ENV"` trước khi cài vào môi trường khác.

### 3. Build torchvision

```bash
python -m pip install 'pillow==10.4.0' 'requests==2.32.3'
vision_build_dir=$(mktemp -d /tmp/robot-torchvision.XXXXXX)
git clone --depth 1 --branch v0.15.1 https://github.com/pytorch/vision.git "$vision_build_dir"
cd "$vision_build_dir"
CUDA_HOME=/usr/local/cuda FORCE_CUDA=1 TORCH_CUDA_ARCH_LIST=8.7 \
  BUILD_VERSION=0.15.1 MAX_JOBS=2 \
  python -m pip install --no-build-isolation --no-deps .
```

`8.7` là kiến trúc GPU của Orin; không dùng cho Jetson Nano đời cũ.
`--no-deps` tránh thay NVIDIA torch, còn `--no-build-isolation` dùng torch và
công cụ build trong chính venv. Vì vậy phải cài `wheel` ở bước 1 trước.

Nếu gặp `invalid command 'bdist_wheel'`, chạy lại lệnh cài pip/setuptools/wheel
ở bước 1, rồi chạy lại lệnh build ngay trong thư mục source torchvision hiện tại.
Không cần clone lại. Cảnh báo thiếu NVJPEG hoặc video codec support không phải
nguyên nhân của lỗi `bdist_wheel`. Nếu hết RAM khi build, giảm `MAX_JOBS=1`.

### 4. Cài profile và chuẩn bị checkpoint

```bash
cd ~/Daikai_Robot_Hub_v2
export PIP_CONSTRAINT="$PWD/deploy/jetpack5/constraints.txt"
python -m pip install -r deploy/jetpack5/requirements.txt
python -m pip check
```

Giữ constraints khi cài thêm package trong profile này. Các file cần có dưới
`backend/r1_yolo_world_stereo/`:

| File | Mục đích |
| --- | --- |
| `yolov8s-worldv2.pt` | Checkpoint YOLO-World dùng để phát hiện vật thể trong ảnh. |
| `r1_stereo_calibration.npz` | Thông số hiệu chỉnh đúng cặp camera để xử lý stereo và tính khoảng cách. |
| `weights/clip/ViT-B-32.pt` | Trọng số CLIP mã hóa nhãn văn bản cho custom prompt; không dùng để hiệu chỉnh camera hay tính khoảng cách. |

CLIP cache không nằm trong Git. Copy từ deployment cũ hoặc chạy kiểm tra
custom prompt khi có internet để tải trước khi đưa Jetson offline. Nếu muốn
đổi checkpoint YOLO, cần kiểm tra cấu hình model và tính tương thích riêng;
chỉ đổi tên file không đảm bảo hoạt động.

### 5. Kiểm tra và khởi động

```bash
cd ~/Daikai_Robot_Hub_v2
python deploy/jetpack5/check_gpu.py
python -m unittest discover -s tests -p 'test_python38_deployment.py'

export CYCLONEDDS_HOME="$HOME/cyclonedds/install"
export CMAKE_PREFIX_PATH="$CYCLONEDDS_HOME${CMAKE_PREFIX_PATH:+:$CMAKE_PREFIX_PATH}"
export LD_LIBRARY_PATH="$CYCLONEDDS_HOME/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
R1_YOLO_DEVICE=cuda:0 python backend eth10 --port 8010
```

SDK phải được cài trong cùng venv theo phần Unitree phía trên. Thay `eth10`
bằng interface nối robot thực tế. Port `8010` khớp proxy của frontend hiện tại.
GPU check kiểm tra CUDA NMS, YOLO-World và FastAPI, không điều khiển robot.
Sau khi kiểm tra thành công, mở frontend và bật stereo để kiểm tra ảnh và khoảng cách.

### Phân biệt lỗi mạng với lỗi cài package

- `ECONNREFUSED 127.0.0.1:8010`: frontend chưa kết nối được backend tại port đó.
- HTTP `409` với `Another robot service request is in progress`: một yêu cầu
  khác đang giữ khóa; đóng các tab web, đợi rồi kiểm tra lại.
- `ServiceList failed with code 3102`: SDK báo lỗi gửi yêu cầu. Kiểm tra
  interface, kết nối DDS và dịch vụ robot; không kết luận thiếu torch hay SDK.
- `ip neigh` hiện `FAILED`: chưa phân giải được MAC của địa chỉ đó trên mạng
  cục bộ. Kiểm tra dây/cổng/nguồn, IP và subnet thực tế của robot.
- `ufw: command not found`: chưa cài công cụ UFW; không cần cài nó để sửa DDS,
  và kết quả này không chứng minh máy không có firewall khác.

Kiểm tra chỉ đọc khi gặp lỗi kết nối:

```bash
ip -br addr
ip route
ip neigh show dev eth10
cat /sys/class/net/eth10/carrier
curl --max-time 15 -i http://127.0.0.1:8010/api/robot/services
```
