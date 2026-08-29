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
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.6/install.sh | bash
source ~/.bashrc
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

## 3. Set up the backend

From the project root, create a Python virtual environment and install the
dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

For local development without a robot connection, start the backend with:

```bash
python backend/app.py
```

The API will run at `http://localhost:8000`.

To connect to a Unitree R1, install Unitree SDK2 Python separately and start the
backend with the network interface connected to the robot:

```bash
python3 backend <robot-network-interface>
```

For example:

```bash
python3 backend eth0
```

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
