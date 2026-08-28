# How to Start on PC Robot

## Step 1: Activate the environment

```bash
cd ~/Daikai_Robot_Hub/
source .venv/bin/activate
```

## Step 2: Run the backend

```bash
cd ~/Daikai_Robot_Hub_v2/
export FR_CORS_ORIGINS=http://192.168.0.75:5173,http://localhost:5173,http://127.0.0.1:5173
python3 -m backend eth10 --host 0.0.0.0 --port 8000
```

## Step 3: Run the frontend

In a second terminal:

```bash
source ~/.bashrc
node --version
```

Confirm that Node.js 22 is installed, then run:

```bash
cd /home/unitree/Daikai_Robot_Hub_v2/frontend
VITE_API_URL=http://192.168.0.75:8000 npm run dev
```

## Step 4: Access the application

Access the application through the `dsing_MR24` link.
