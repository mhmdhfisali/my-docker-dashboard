import re
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import docker

app = FastAPI(title="Docker Dashboard")
templates = Jinja2Templates(directory="templates")

# Inisialisasi Docker Client dari Environment Host
try:
    client = docker.from_env()
except Exception as e:
    print(f"Warning: Gagal terhubung ke Docker Socket: {e}")
    client = None


def parse_ports(container):
    """Ekstrak port publik (host ports) dari container."""
    ports = []
    if not container.attrs.get("NetworkSettings", {}).get("Ports"):
        return ports

    port_bindings = container.attrs["NetworkSettings"]["Ports"]
    for container_port, host_bindings in port_bindings.items():
        if host_bindings:
            for binding in host_bindings:
                host_port = binding.get("HostPort")
                if host_port and host_port not in ports:
                    ports.append(host_port)
    return ports


def get_stack_prefix(name: str) -> str:
    """Ekstrak prefix stack secara konsisten."""
    if "-" in name:
        parts = name.split("-")
        return f"{parts[0]}-{parts[1]}" if len(parts) >= 3 else parts[0]
    elif "_" in name:
        return name.split("_")[0]
    return name


class ToggleRequest(BaseModel):
    prefix: str = None
    action: str


class TunnelStartRequest(BaseModel):
    containerName: str
    port: str


class TunnelStopRequest(BaseModel):
    tunnelName: str


@app.get("/", response_class=HTMLResponse)
async def serve_index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


@app.get("/api/status")
async def get_status():
    if not client:
        raise HTTPException(status_code=500, detail="Docker Engine tidak terdeteksi")

    raw_containers = client.containers.list(all=True)
    stacks = {}
    total_running = 0

    for c in raw_containers:
        name = c.name
        is_running = c.status == "running"
        if is_running:
            total_running += 1

        # Abaikan container tunnel publik otomatis
        if name.startswith("tunnel-"):
            continue

        prefix = get_stack_prefix(name)

        if prefix not in stacks:
            stacks[prefix] = {
                "prefix": prefix,
                "name": f"{prefix.upper()} Stack",
                "containers": [],
                "isRunning": False,
            }

        ports = parse_ports(c)
        stacks[prefix]["containers"].append(
            {"name": name, "isRunning": is_running, "ports": ports}
        )

        if is_running:
            stacks[prefix]["isRunning"] = True

    # Hitung CPU & Memory Usage
    total_cpu = 0.0
    mem_summary = "Active"

    running_containers = [c for c in raw_containers if c.status == "running"]
    for c in running_containers:
        try:
            stats = c.stats(stream=False)

            # Hitung % CPU secara manual dari stats
            cpu_delta = (
                stats["cpu_stats"]["cpu_usage"]["total_usage"]
                - stats["precpu_stats"]["cpu_usage"]["total_usage"]
            )
            system_delta = stats["cpu_stats"].get("system_cpu_usage", 0) - stats[
                "precpu_stats"
            ].get("system_cpu_usage", 0)
            online_cpus = stats["cpu_stats"].get("online_cpus", 1)

            if system_delta > 0.0 and cpu_delta > 0.0:
                cpu_percent = (cpu_delta / system_delta) * online_cpus * 100.0
                total_cpu += cpu_percent

            # Ambil Memory Usage dari container pertama yang ditemui
            if mem_summary == "Active" and "memory_stats" in stats:
                usage = stats["memory_stats"].get("usage", 0) / (1024 * 1024)
                limit = stats["memory_stats"].get("limit", 1) / (1024 * 1024)
                mem_summary = f"{usage:.1f}MB / {limit:.0f}MB"
        except Exception:
            pass

    return {
        "stacks": stacks,
        "totalRunning": total_running,
        "totalContainers": len(raw_containers),
        "cpuUsage": f"{total_cpu:.1f}%",
        "memUsage": mem_summary,
    }


@app.post("/api/tunnel/start")
async def start_tunnel(req: TunnelStartRequest):
    tunnel_name = f"tunnel-{req.containerName}-{req.port}"
    try:
        try:
            existing = client.containers.get(tunnel_name)
            existing.start()
        except docker.errors.NotFound:
            client.containers.run(
                image="cloudflare/cloudflared:latest",
                command=f"tunnel --url http://127.0.0.1:{req.port}",
                name=tunnel_name,
                detach=True,
                network_mode="host",
                restart_policy={"Name": "no"},
            )
        return {"message": "Tunnel starting", "tunnelName": tunnel_name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/tunnel/url/{tunnel_name}")
async def get_tunnel_url(tunnel_name: str):
    try:
        container = client.containers.get(tunnel_name)
        logs = container.logs(tail=50).decode("utf-8", errors="ignore")
        match = re.search(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com", logs)
        return {"url": match.group(0) if match else None}
    except Exception:
        return {"url": None}


@app.post("/api/tunnel/stop")
async def stop_tunnel(req: TunnelStopRequest):
    try:
        container = client.containers.get(req.tunnelName)
        container.stop()
        return {"message": "Tunnel stopped"}
    except Exception as e:
        return {"message": f"Error or already stopped: {e}"}


@app.get("/api/logs/{name}")
async def get_logs(name: str):
    try:
        container = client.containers.get(name)
        logs = container.logs(tail=100).decode("utf-8", errors="ignore")
        return {"logs": logs if logs else "Belum ada log tercatat."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/toggle")
async def toggle_stack(req: ToggleRequest):
    if req.action == "stop_all":
        for c in client.containers.list(filters={"status": "running"}):
            c.stop()
        return {"message": "All stopped"}

    raw_containers = client.containers.list(all=True)
    target_containers = [
        c
        for c in raw_containers
        if get_stack_prefix(c.name).lower() == req.prefix.lower()
    ]

    if not target_containers:
        raise HTTPException(status_code=404, detail="Stack not found")

    for c in target_containers:
        if req.action == "start":
            c.start()
        else:
            c.stop()

    return {"message": "Success"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=3000, reload=True)
