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

### 4. Cài profile, kiểm tra GPU và Python 3.8

Sau khi torchvision build thành công, giữ `(.venv)` đang bật và chạy lần lượt:

```bash
cd ~/Daikai_Robot_Hub_v2
export PIP_CONSTRAINT="$PWD/deploy/jetpack5/constraints.txt"
python -m pip install -r deploy/jetpack5/requirements.txt
python -m pip check
python deploy/jetpack5/check_gpu.py
python -m unittest discover -s tests -p 'test_python38_deployment.py'
```

`pip check` kiểm tra xung đột dependency; `check_gpu.py` kiểm tra CUDA NMS,
YOLO-World custom prompt và FastAPI; unittest kiểm tra tương thích Python 3.8
và cách nạp CLIP. Các kiểm tra này không điều khiển robot. Dừng nếu có lỗi.
Lần kiểm tra model đầu tiên cần internet nếu chưa có CLIP cache.

Nếu unittest báo annotation `dict[...]` trong backend chưa tương thích, đồng bộ
code đã sửa từ GitHub sang Jetson rồi chạy lại test; không cần build lại
torchvision chỉ vì lỗi annotation. Nếu có thay đổi code cục bộ, lưu lại trước
khi cập nhật bằng `git pull`.

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

### 5. Khởi động sau khi các kiểm tra thành công

```bash
cd ~/Daikai_Robot_Hub_v2
export CYCLONEDDS_HOME="$HOME/cyclonedds/install"
export CMAKE_PREFIX_PATH="$CYCLONEDDS_HOME${CMAKE_PREFIX_PATH:+:$CMAKE_PREFIX_PATH}"
export LD_LIBRARY_PATH="$CYCLONEDDS_HOME/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
R1_YOLO_DEVICE=cuda:0 python backend eth10 --port 8010
```

SDK phải được cài trong cùng venv theo phần Unitree phía trên. Thay `eth10`
bằng interface nối robot thực tế. Port `8010` khớp proxy của frontend hiện tại.
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

## XR teleoperation: môi trường riêng cho `robot_teleoperation.py`

`backend/robot_teleoperation.py` là bộ quản lý subprocess được backend gọi qua
web, không phải script chạy độc lập bằng `python backend/robot_teleoperation.py`.
Nó chạy bản tùy chỉnh `reference_script/teleop_hand_and_arm.py` của dự án,
nhưng vẫn cần modules và robot assets từ repo Unitree `xr_teleoperate`.

### Những thành phần bắt buộc

| Thành phần | Mục đích |
| --- | --- |
| Miniconda Linux aarch64 tại `/home/unitree/miniconda3` | Cung cấp môi trường XR độc lập trên Jetson ARM64. |
| Conda environment `tv`, Python 3.10 | Runtime cho XR; không thay `.venv` Python 3.8 đang dùng stereo. |
| `xr_teleoperate` và submodules | Controller R1, inverse kinematics, URDF/mesh assets, IPC và XR transport. |
| Pinocchio 3.1.0 | Tính động học robot / inverse kinematics. |
| `televuer` và HTTPS certificate | Nhận pose tay/controller từ kính XR qua kết nối bảo mật. |
| `teleimager`, `libjpeg-turbo` | Thư viện camera XR; bản script đã sửa chỉ import API camera cũ khi bật image server. |
| Unitree SDK2 + Cyclone DDS trong `tv` | Gửi lệnh robot từ subprocess; bản cài trong `.venv` không tự xuất hiện trong Conda. |
| `pyzmq` ở backend và `tv` | Kết nối nút Start/Stop trên web với tiến trình XR qua IPC. |
| Kính XR hỗ trợ và kết nối mạng tới Jetson | Nguồn dữ liệu hand/controller tracking; trang web Robot Hub không tự tạo pose XR. |

Hướng dẫn nguồn: [Unitree xr_teleoperate](https://github.com/unitreerobotics/xr_teleoperate#1--installation).
Profile này chưa được xác minh trên phần cứng từ workspace này. Dùng revision
có các controller `R1_A5`/`R1_A7` và giữ submodules đúng commit của revision đó.

### 1. Chuẩn bị Conda và source

Nếu chưa có Miniconda, cài bản **Linux aarch64** theo
[hướng dẫn Miniconda](https://www.anaconda.com/docs/getting-started/miniconda/install)
vào `/home/unitree/miniconda3`. Không tải installer Linux x86_64 cho Jetson.
Mở terminal riêng để cài XR, không cài các package này vào `.venv` stereo:

```bash
source /home/unitree/miniconda3/etc/profile.d/conda.sh
# Chỉ tạo khi chưa có environment tv:
conda create -n tv python=3.10 pinocchio=3.1.0 numpy=1.26.4 -c conda-forge
conda activate tv
# Không mang constraints torch/Python 3.8 sang environment XR:
unset PIP_CONSTRAINT
cd /home/unitree
git clone https://github.com/unitreerobotics/xr_teleoperate.git
cd xr_teleoperate
git submodule update --init --recursive
```

Nếu đã có source/environment hoạt động, giữ lại và kiểm tra thay vì tạo đè.
Không chạy freeze/requirements của stereo trong environment `tv`.

### 2. Cài submodules và SDK trong `tv`

Trước hết cài requirements của repo XR, không chỉ requirements của Robot Hub.
File này chứa `matplotlib`, `meshcat`, `sshkeyboard` và `rerun-sdk` theo phiên
bản của checkout. Module lọc import matplotlib ngay khi nạp; module IK import
meshcat dù không bật visualization. CasADi và binding Pinocchio/CasADi phục vụ
bài toán inverse kinematics. Không dùng `pip install pinocchio` để thay bản
Pinocchio đã cài bằng conda-forge.

```bash
conda activate tv
unset PIP_CONSTRAINT
conda install -c conda-forge 'python=3.10' 'pinocchio=3.1.0' 'numpy=1.26.4' casadi libjpeg-turbo
cd /home/unitree/xr_teleoperate
python -m pip install -r requirements.txt
python -m pip install logging_mp pyzmq pyyaml aiohttp aiohttp-cors 'params-proto==2.13.2'
```

Với Vuer 0.0.60, pin `params-proto==2.13.2` cung cấp API `Flag`, `PrefixProto`
và `Proto`. Thông báo Vuer thiếu aiohttp là thông báo chung bắt mọi ImportError,
nên có thể che lỗi phiên bản params-proto. `pip check` không phát hiện được
mọi lỗi import/API. Nếu dùng revision XR/Vuer khác, xác minh pin lại thay vì
nâng toàn bộ package một cách tự động.

```bash
conda install -c conda-forge libjpeg-turbo
cd /home/unitree/xr_teleoperate/teleop/teleimager
python -m pip install -e .
cd /home/unitree/xr_teleoperate/teleop/televuer
python -m pip install -e .

export CYCLONEDDS_HOME="$HOME/cyclonedds/install"
export CMAKE_PREFIX_PATH="$CYCLONEDDS_HOME${CMAKE_PREFIX_PATH:+:$CMAKE_PREFIX_PATH}"
export LD_LIBRARY_PATH="$CYCLONEDDS_HOME/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
python -m pip install -e /home/unitree/unitree_sdk2_python
python -m pip check
```

Cài các dependency còn lại theo README/metadata của revision XR đã checkout.
Theo README upstream được kiểm tra khi viết phần này, teleimager được pin ở
v2.0.8; không tự nâng lên 2.1.x vì có thay đổi API không tương thích.

### 3. HTTPS cho kính XR

Với PICO/Quest, nếu chưa có certificate, tạo trong thư mục mới để không ghi đè
certificate đang dùng:

```bash
xr_cert_dir=$(mktemp -d "$HOME/xr-certs.XXXXXX")
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout "$xr_cert_dir/key.pem" -out "$xr_cert_dir/cert.pem"
export XR_TELEOP_CERT="$xr_cert_dir/cert.pem"
export XR_TELEOP_KEY="$xr_cert_dir/key.pem"
```

Cho backend kế thừa hai biến certificate khi khởi động, hoặc cấu hình certificate
ở `~/.config/xr_teleoperate/` theo README upstream. Với Apple Vision Pro, dùng
quy trình root CA và SAN chứa IP host trong README upstream, không dùng nguyên
quy trình PICO/Quest ở trên. Kính phải truy cập được HTTPS/WebSocket port `8012`
của máy chạy XR. Launcher hiện dùng pass-through, không cần chạy image server,
bản script đã sửa không import ImageClient cũ trong chế độ này.

### 4. Kiểm tra trước khi bật từ web

Các đường dẫn sau đang hard-code trong `backend/robot_teleoperation.py`:

- Conda: `/home/unitree/miniconda3/etc/profile.d/conda.sh`.
- Working directory: `/home/unitree/xr_teleoperate/teleop`.
- Environment: `tv`; robot arm: `R1_A5`; interface: `eth10`.
- Tần số điều khiển: 30 Hz; input: hand hoặc controller; bật `--motion --ipc`.

Tần số 30 Hz này là vòng điều khiển XR, không phải FPS YOLO/stereo. Nếu robot
là R1_A7 hoặc interface khác, phải sửa launcher trước khi chạy; tham số interface
của backend không tự thay `eth10` hard-code của XR launcher.

Kiểm tra toàn bộ import, chưa chạy khối main khởi tạo controller robot:

```bash
source /home/unitree/miniconda3/etc/profile.d/conda.sh
conda activate tv
cd /home/unitree/xr_teleoperate/teleop
python - <<'PY'
import runpy
from params_proto import Flag, PrefixProto, Proto
from vuer.server import Vuer, VuerSession
import casadi
from pinocchio import casadi as cpin
runpy.run_path(
    '/home/unitree/Daikai_Robot_Hub_v2/reference_script/teleop_hand_and_arm.py',
    run_name='teleop_import_check',
)
print('Teleoperation imports OK')
PY
python -m pip check
```

Vuer có thể bắt `--help` ngay lúc import, in help riêng rồi thoát trước các
import phía sau. Vì vậy dùng phép kiểm tra `runpy` ở trên thay vì coi `--help`
là bằng chứng đã đủ dependency. Nếu báo thiếu module hoặc controller, sửa
environment/revision XR đó trước. Phép kiểm tra import chưa đảm bảo toàn bộ
assets và kết nối runtime. Các dependency của end effector tùy chọn (Dex/Inspire/
BrainCo) hoặc recording cần cài thêm theo revision upstream nếu bật các chế độ
đó; launcher hiện không truyền `--ee` hoặc `--record`.
Sau đó chạy backend trong `.venv` Python 3.8 như bình thường với các biến DDS và
certificate, dùng bảng Teleoperation trên web để launch và bắt đầu tracking.
Không chạy thêm một instance điều khiển XR song song.


### Sửa lỗi `No module named teleimager.image_client`

Teleimager 2.0.8 cung cấp `teleimager.client.TeleImageClient`, không cung cấp
API cũ `teleimager.image_client.ImageClient`. Cài lại cùng phiên bản không sửa
được khác biệt API này; không đổi tên import thành alias vì constructor và các
phương thức lấy ảnh cũng khác nhau.

Đồng bộ bản sửa `reference_script/teleop_hand_and_arm.py` từ repository sang
Jetson. Bản sửa chỉ import ImageClient cũ trong nhánh dùng image server, nên
launcher web với `--no-image-server --display-mode=pass-through` không bị chặn.
Chạy lại phép kiểm tra `runpy` ở trên sau khi đồng bộ. Chế độ image server cũ
chưa được chuyển sang TeleImageClient 2.x và sẽ báo lỗi rõ ràng nếu sử dụng.
