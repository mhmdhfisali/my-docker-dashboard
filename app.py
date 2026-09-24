import os
import re
import asyncio
import subprocess
from typing import Dict, Optional, List
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import docker
import psutil

app = FastAPI(title="Docker Dashboard")
templates = Jinja2Templates(directory="templates")

try:
    client = docker.from_env()
except Exception as e:
    print(f"Warning: Gagal terhubung ke Docker Engine Socket: {e}")
    client = None

active_tunnels: Dict[str, dict] = {}


def parse_ports(container) -> List[str]:
    ports = []
    network_settings = container.attrs.get("NetworkSettings", {})
    port_bindings = network_settings.get("Ports") or {}

    for container_port, host_bindings in port_bindings.items():
        if host_bindings:
            for binding in host_bindings:
                host_port = binding.get("HostPort")
                if host_port and host_port not in ports:
                    ports.append(host_port)
    return ports


def get_stack_info(container) -> tuple[str, Optional[str]]:
    """Mengambil nama stack dan working directory dari label Docker Compose."""
    labels = container.labels or {}
    stack_name = labels.get("com.docker.compose.project")
    working_dir = labels.get("com.docker.compose.project.working_dir")

    if not stack_name:
        name = container.name.lstrip("/")
        if "-" in name:
            stack_name = name.split("-")[0]
        elif "_" in name:
            stack_name = name.split("_")[0]
        else:
            stack_name = name

    return stack_name.lower(), working_dir


def get_git_info(target_dir: str) -> dict:
    """Mengambil detail Git dari direktori project."""
    if not target_dir or not os.path.exists(target_dir):
        return {
            "hasGit": False,
            "repoUrl": "N/A",
            "branch": "N/A",
            "lastCommit": "N/A",
            "commitDate": "N/A",
        }

    def run_cmd(args):
        try:
            res = subprocess.run(
                ["git"] + args,
                cwd=target_dir,
                capture_output=True,
                text=True,
                check=True,
            )
            return res.stdout.strip()
        except Exception:
            return ""

    repo_url = run_cmd(["config", "--get", "remote.origin.url"])
    branch = run_cmd(["rev-parse", "--abbrev-ref", "HEAD"])
    last_commit = run_cmd(["log", "-1", "--format=%s (%h)"])
    commit_date = run_cmd(["log", "-1", "--format=%cr"])

    return {
        "hasGit": bool(repo_url or branch),
        "repoUrl": repo_url or "Belum set remote origin",
        "branch": branch or "main",
        "lastCommit": last_commit or "Belum ada commit",
        "commitDate": commit_date or "Terbaru",
    }


class ToggleRequest(BaseModel):
    prefix: Optional[str] = None
    action: str  # 'start', 'stop', 'stop_all'


class ContainerActionRequest(BaseModel):
    containerName: str
    action: str  # 'start', 'stop', 'restart', 'remove'


class TunnelStartRequest(BaseModel):
    containerName: str
    port: str


class TunnelStopRequest(BaseModel):
    tunnelName: str


class GitActionRequest(BaseModel):
    projectPath: str
    commitMessage: Optional[str] = "Update project via Dashboard"
    action: str = "push"  # 'push', 'pull', 'set_remote'
    remoteUrl: Optional[str] = None


@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


@app.get("/api/status")
async def get_status():
    if not client:
        return JSONResponse(
            status_code=500, content={"error": "Docker Client tidak terhubung"}
        )

    try:
        containers = client.containers.list(all=True)
        stacks: Dict[str, dict] = {}
        total_running = 0

        for c in containers:
            container_name = c.name.lstrip("/")
            if container_name.startswith("tunnel-"):
                continue

            is_running = c.status == "running"
            if is_running:
                total_running += 1

            stack_key, working_dir = get_stack_info(c)
            if stack_key == "tunnel":
                continue

            if stack_key not in stacks:
                git_meta = (
                    get_git_info(working_dir)
                    if working_dir
                    else {
                        "hasGit": False,
                        "repoUrl": "N/A",
                        "branch": "N/A",
                        "lastCommit": "N/A",
                        "commitDate": "N/A",
                    }
                )
                stacks[stack_key] = {
                    "prefix": stack_key,
                    "name": stack_key.upper(),
                    "workingDir": working_dir or "",
                    "gitInfo": git_meta,
                    "isRunning": False,
                    "containers": [],
                }
            elif not stacks[stack_key]["workingDir"] and working_dir:
                stacks[stack_key]["workingDir"] = working_dir
                stacks[stack_key]["gitInfo"] = get_git_info(working_dir)

            ports = parse_ports(c)
            stacks[stack_key]["containers"].append(
                {
                    "name": container_name,
                    "status": c.status,
                    "isRunning": is_running,
                    "ports": ports,
                }
            )

            if is_running:
                stacks[stack_key]["isRunning"] = True

        cpu_usage = f"{psutil.cpu_percent()}%"
        mem = psutil.virtual_memory()
        mem_usage = f"{mem.used / (1024**3):.1f}GB / {mem.total / (1024**3):.1f}GB"
        mem_percent = f"{mem.percent}%"

        return {
            "totalRunning": total_running,
            "cpuUsage": cpu_usage,
            "memUsage": mem_usage,
            "memPercent": mem_percent,
            "stacks": stacks,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/toggle")
async def toggle_stack(req: ToggleRequest):
    if not client:
        raise HTTPException(status_code=500, detail="Docker Client offline")

    containers = client.containers.list(all=True)

    if req.action == "stop_all":
        for c in containers:
            if c.status == "running":
                c.stop()
        return {"status": "success", "message": "Semua container dihentikan"}

    if not req.prefix:
        raise HTTPException(status_code=400, detail="Prefix stack diperlukan")

    target_containers = [
        c for c in containers if get_stack_info(c)[0] == req.prefix.lower()
    ]

    for c in target_containers:
        if req.action == "start":
            c.start()
        elif req.action == "stop":
            c.stop()

    return {"status": "success", "message": f"Stack {req.prefix} {req.action} berhasil"}


@app.post("/api/container/action")
async def container_action(req: ContainerActionRequest):
    if not client:
        raise HTTPException(status_code=500, detail="Docker Client offline")

    try:
        container = client.containers.get(req.containerName)
        if req.action == "start":
            container.start()
        elif req.action == "stop":
            container.stop()
        elif req.action == "restart":
            container.restart()
        elif req.action == "remove":
            container.remove(force=True)
        return {
            "status": "success",
            "message": f"Container {req.containerName} {req.action} berhasil",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/git/action")
async def git_action(req: GitActionRequest):
    target_dir = req.projectPath
    if not target_dir or not os.path.exists(target_dir):
        raise HTTPException(
            status_code=400, detail=f"Direktori project tidak ditemukan: {target_dir}"
        )

    def run_git(args):
        return subprocess.run(
            ["git"] + args, cwd=target_dir, capture_output=True, text=True, check=True
        )

    try:
        if req.action == "set_remote":
            if not req.remoteUrl:
                raise HTTPException(
                    status_code=400, detail="URL Repository baru tidak boleh kosong."
                )

            # Cek apakah remote origin sudah ada
            try:
                run_git(["remote", "set-url", "origin", req.remoteUrl])
            except Exception:
                run_git(["remote", "add", "origin", req.remoteUrl])

            return {
                "status": "success",
                "message": f"Berhasil mengubah remote origin ke: {req.remoteUrl}",
            }

        if req.action == "pull":
            res = run_git(["pull"])
            return {
                "status": "success",
                "message": "Berhasil Git Pull!",
                "output": res.stdout or res.stderr,
            }

        run_git(["add", "."])
        commit_res = run_git(["commit", "-m", req.commitMessage or "Update project"])
        push_res = run_git(["push"])

        return {
            "status": "success",
            "message": "Berhasil commit & push ke GitHub!",
            "output": f"{commit_res.stdout}\n{push_res.stdout}",
        }
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr or e.stdout or str(e)
        if "nothing to commit" in error_msg.lower():
            return {
                "status": "success",
                "message": "Tidak ada perubahan baru untuk di-commit.",
                "output": error_msg,
            }
        raise HTTPException(status_code=500, detail=f"Git Error: {error_msg}")


@app.get("/api/logs/{container_name}")
async def get_logs(container_name: str):
    if not client:
        raise HTTPException(status_code=500, detail="Docker Client offline")

    try:
        container = client.containers.get(container_name)
        logs = container.logs(tail=200).decode("utf-8", errors="ignore")
        return {"logs": logs}
    except Exception as e:
        return {"logs": f"Gagal membaca log: {str(e)}"}


@app.post("/api/tunnel/start")
async def start_tunnel(req: TunnelStartRequest):
    tunnel_name = f"tunnel-{req.containerName}-{req.port}"

    if tunnel_name in active_tunnels:
        return {"status": "already_running", "tunnelName": tunnel_name}

    try:
        proc = subprocess.Popen(
            ["cloudflared", "tunnel", "--url", f"http://localhost:{req.port}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        active_tunnels[tunnel_name] = {"process": proc, "url": None}

        async def capture_url():
            while True:
                line = proc.stderr.readline()
                if not line:
                    break
                match = re.search(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com", line)
                if match:
                    active_tunnels[tunnel_name]["url"] = match.group(0)
                    break
                await asyncio.sleep(0.1)

        asyncio.create_task(capture_url())
        return {"status": "started", "tunnelName": tunnel_name}

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Gagal memulai cloudflared: {str(e)}"
        )


@app.get("/api/tunnel/url/{tunnel_name}")
async def get_tunnel_url(tunnel_name: str):
    tunnel_info = active_tunnels.get(tunnel_name)
    if not tunnel_info:
        return {"url": None}
    return {"url": tunnel_info.get("url")}


@app.post("/api/tunnel/stop")
async def stop_tunnel(req: TunnelStopRequest):
    tunnel_info = active_tunnels.get(req.tunnelName)
    if tunnel_info:
        proc = tunnel_info.get("process")
        if proc:
            proc.terminate()
        del active_tunnels[req.tunnelName]
        return {"status": "stopped"}
    return {"status": "not_found"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=3000, reload=True)
