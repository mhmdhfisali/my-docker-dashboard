# 🐳 Docker Control Center Pro (v5.0 Pro Hub)

A modern, fast, and feature-rich Web Dashboard built to monitor and manage Docker containers, multi-stack services, and public Cloudflare Tunnels seamlessly with integrated per-project Git management.

![Docker Control Center](https://img.shields.io/badge/Docker-Control%20Center-sky?style=for-the-badge&logo=docker)
![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi)
![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-38B2AC?style=for-the-badge&logo=tailwind-css)
![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python)

---

## 🌟 Key Features

- 📊 **Real-time Server Metrics**: Monitor CPU Load, RAM Usage, Running Containers, and Total Stacks dynamically.
- ⚡ **Multi-Stack & Container Management**: Easily start, stop, restart, or delete individual containers or full stacks with a single click.
- 🔗 **Cloudflare Public Tunnel Integration**: Expose any container port to a public HTTPS URL instantly with automatic status tracking.
- 🐙 **Per-Project Git Sync**: Pull latest updates, change remote origin URLs, or commit & push changes directly from the UI modal.
- 📜 **Interactive Container Logs**: Real-time log viewer with live search/filter and copy-to-clipboard functionality.
- 🎨 **Modern Dark/Light UI**: Built with Tailwind CSS, FontAwesome icons, responsive layouts, and auto-refresh toggles.
- ⚙️ **Auto-Start Systemd Integration**: Runs automatically on system boot as a background service on port `3000`.

---

## 🛠️ Tech Stack

- **Backend**: Python 3, FastAPI, Uvicorn, Docker SDK for Python
- **Frontend**: HTML5, Tailwind CSS (via CDN), FontAwesome 6, JavaScript (Vanilla ES6)
- **Deployment**: Systemd Service, Linux Environment (CachyOS / Arch Linux)

---

## 📁 Project Structure

```text
my-docker-dashboard/
├── app.py              # Main FastAPI application backend
├── main.py             # Alternative entry point / Docker client setup
├── requirements.txt    # Python dependencies
├── templates/
│   └── index.html      # Dashboard UI (Tailwind CSS & Vanilla JS)
└── venv/               # Python Virtual Environment

```

---

## 🚀 Quick Start (Local Setup)

### 1. Prerequisites

Ensure you have Python 3 and Docker installed and running on your system:

```bash
docker --version
python3 --version

```

### 2. Installation

Clone the repository and navigate into the project directory:

```bash
git clone [https://github.com/username/my-docker-dashboard.git](https://github.com/username/my-docker-dashboard.git)
cd my-docker-dashboard

```

Create and activate a Python virtual environment:

```bash
python -m venv venv
source venv/bin/activate.fish   # For Fish shell
# OR
source venv/bin/activate        # For Bash/Zsh

```

Install the required dependencies:

```bash
pip install -r requirements.txt

```

### 3. Running the Server

Run the application manually:

```bash
python app.py

```

Open your browser and navigate to: **`http://localhost:3000`**

---

## 🔄 Auto-Start on Boot (Systemd Setup)

To make the dashboard run automatically on port `3000` whenever your machine boots or restarts (without opening a terminal), set up a Systemd service:

### 1. Create Service File

```bash
sudo nano /etc/systemd/system/docker-dashboard.service

```

### 2. Paste Configuration

```ini
[Unit]
Description=Docker Control Center Pro Dashboard
After=network.target docker.service
Requires=docker.service

[Service]
Type=simple
User=absolutelie
WorkingDirectory=/home/absolutelie/my-docker-dashboard
ExecStart=/home/absolutelie/my-docker-dashboard/venv/bin/python app.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target

```

### 3. Enable and Start

```bash
sudo systemctl daemon-reload
sudo systemctl enable docker-dashboard.service
sudo systemctl start docker-dashboard.service

```

### 4. Check Status

```bash
sudo systemctl status docker-dashboard.service

```

---

## 📡 API Endpoints

| Method | Endpoint                    | Description                                                            |
| ------ | --------------------------- | ---------------------------------------------------------------------- |
| `GET`  | `/`                         | Renders the Dashboard Web UI                                           |
| `GET`  | `/api/status`               | Fetches container statuses, stack info, and server resource usage      |
| `POST` | `/api/toggle`               | Starts/stops entire stacks or stops all containers                     |
| `POST` | `/api/container/action`     | Executes actions (`start`, `stop`, `restart`, `remove`) on a container |
| `GET`  | `/api/logs/{containerName}` | Retrieves logs for a specific container                                |
| `POST` | `/api/tunnel/start`         | Launches a Cloudflare Tunnel for a specified port                      |
| `POST` | `/api/tunnel/stop`          | Terminates an active Cloudflare Tunnel                                 |
| `POST` | `/api/git/action`           | Executes Git actions (`push`, `pull`, `set_remote`)                    |

---

## 📄 License

Distributed under the MIT License. Feel free to modify and use it for your personal infrastructure.

```

```
# my-docker-dashboard
