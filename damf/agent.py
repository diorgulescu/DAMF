#!/usr/bin/env python3
"""DAMF Target Heartbeat & Telemetry Agent.

Can run standalone on any embedded Linux/Unix board with zero external dependencies:
    python3 agent.py --server http://192.168.10.1:8080 --name rpi4-lab-01 --interval 15

Also provides a POSIX `/bin/sh` / BusyBox script generator (`generate_posix_shell_agent`)
for ultra-constrained embedded targets (TI Sitara, Buildroot, OpenWrt) without Python.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import socket
import subprocess
import time
from typing import Any
import urllib.error
import urllib.request


def _read_loadavg() -> tuple[float, float, float]:
    """Return (load_1m, load_5m, load_15m) from /proc/loadavg or os.getloadavg()."""
    proc_load = Path("/proc/loadavg")
    if proc_load.exists():
        try:
            parts = proc_load.read_text(encoding="utf-8").split()
            return round(float(parts[0]), 2), round(float(parts[1]), 2), round(float(parts[2]), 2)
        except (ValueError, IndexError, OSError):
            pass
    if hasattr(os, "getloadavg"):
        try:
            l1, l5, l15 = os.getloadavg()
            return round(l1, 2), round(l5, 2), round(l15, 2)
        except OSError:
            pass
    return 0.0, 0.0, 0.0


def _read_meminfo() -> dict[str, float]:
    """Return memory usage stats (total_mb, used_mb, percent) from /proc/meminfo."""
    meminfo = Path("/proc/meminfo")
    if meminfo.exists():
        try:
            kv: dict[str, int] = {}
            for line in meminfo.read_text(encoding="utf-8").splitlines():
                if ":" in line:
                    k, _, rest = line.partition(":")
                    num = rest.strip().split()[0]
                    kv[k.strip()] = int(num)
            total_kb = kv.get("MemTotal", 0)
            avail_kb = kv.get("MemAvailable", kv.get("MemFree", 0) + kv.get("Buffers", 0) + kv.get("Cached", 0))
            if total_kb > 0:
                used_kb = max(0, total_kb - avail_kb)
                return {
                    "mem_total_mb": round(total_kb / 1024.0, 1),
                    "mem_used_mb": round(used_kb / 1024.0, 1),
                    "mem_percent": round((used_kb / total_kb) * 100.0, 1),
                }
        except (ValueError, OSError):
            pass
    return {"mem_total_mb": 1024.0, "mem_used_mb": 256.0, "mem_percent": 25.0}


def _read_cpu_temp_c() -> float | None:
    """Read SoC temperature in Celsius from /sys/class/thermal/thermal_zone*/temp."""
    for zone in sorted(Path("/sys/class/thermal").glob("thermal_zone*/temp")) if Path("/sys/class/thermal").exists() else []:
        try:
            raw = int(zone.read_text(encoding="utf-8").strip())
            return round(raw / 1000.0 if raw > 200 else float(raw), 1)
        except (ValueError, OSError):
            continue
    return None


def _read_uptime_seconds() -> float:
    """Read system uptime in seconds from /proc/uptime."""
    proc_up = Path("/proc/uptime")
    if proc_up.exists():
        try:
            return round(float(proc_up.read_text(encoding="utf-8").split()[0]), 1)
        except (ValueError, IndexError, OSError):
            pass
    return 0.0


def _read_recent_logs(max_lines: int = 25) -> list[str]:
    """Read the last `max_lines` of system/kernel logs from syslog, messages, or dmesg."""
    for log_file in ("/var/log/syslog", "/var/log/messages", "/var/log/system.log"):
        p = Path(log_file)
        if p.exists() and os.access(p, os.R_OK):
            try:
                lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
                return lines[-max_lines:]
            except OSError:
                pass

    for cmd in (["dmesg"], ["journalctl", "-n", str(max_lines), "--no-pager"]):
        if shutil.which(cmd[0]):
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=3.0, check=False)
                if proc.returncode == 0 and proc.stdout.strip():
                    return proc.stdout.strip().splitlines()[-max_lines:]
            except (OSError, subprocess.SubprocessError):
                pass
    return [f"[{time.strftime('%H:%M:%S')}] kernel: damf-agent heartbeat active"]


def collect_telemetry(
    device_name: str | None = None,
    board_type: str | None = None,
    log_lines: int = 20,
) -> dict[str, Any]:
    """Collect vital target telemetry (CPU load, RAM, Disk, SoC Temp, Uptime, Logs)."""
    load_1m, load_5m, load_15m = _read_loadavg()
    mem = _read_meminfo()
    try:
        du = shutil.disk_usage("/")
        disk_total_gb = round(du.total / (1024**3), 2)
        disk_used_gb = round(du.used / (1024**3), 2)
        disk_percent = round((du.used / du.total) * 100.0, 1) if du.total else 0.0
    except OSError:
        disk_total_gb, disk_used_gb, disk_percent = 0.0, 0.0, 0.0

    temp_c = _read_cpu_temp_c()
    uptime_sec = _read_uptime_seconds()
    hostname = socket.gethostname()

    return {
        "device_name": device_name or hostname,
        "board_type": board_type or "",
        "hostname": hostname,
        "arch": platform.machine() or "arm64",
        "kernel": f"{platform.system()} {platform.release()}".strip(),
        "load_1m": load_1m,
        "load_5m": load_5m,
        "load_15m": load_15m,
        "mem_total_mb": mem["mem_total_mb"],
        "mem_used_mb": mem["mem_used_mb"],
        "mem_percent": mem["mem_percent"],
        "disk_total_gb": disk_total_gb,
        "disk_used_gb": disk_used_gb,
        "disk_percent": disk_percent,
        "cpu_temp_c": temp_c,
        "uptime_seconds": uptime_sec,
        "logs": _read_recent_logs(max_lines=log_lines),
        "timestamp": time.time(),
    }


def generate_posix_shell_agent(
    server_url: str,
    device_name: str,
    interval: int = 15,
) -> str:
    """Generate a minimal POSIX `/bin/sh` / BusyBox heartbeat agent for targets without Python."""
    endpoint = f"{server_url.rstrip('/')}/api/v1/agent/heartbeat"
    return f"""#!/bin/sh
# DAMF Tier-2 Minimal POSIX / BusyBox Target Heartbeat Agent
SERVER_ENDPOINT="{endpoint}"
DEVICE_NAME="{device_name}"
INTERVAL={int(interval)}

send_heartbeat() {{
  LOAD_1M=$(awk '{{print $1}}' /proc/loadavg 2>/dev/null || echo 0.0)
  LOAD_5M=$(awk '{{print $2}}' /proc/loadavg 2>/dev/null || echo 0.0)
  LOAD_15M=$(awk '{{print $3}}' /proc/loadavg 2>/dev/null || echo 0.0)
  UPTIME=$(awk '{{print $1}}' /proc/uptime 2>/dev/null || echo 0)
  MEM_TOTAL=$(awk '/MemTotal/ {{printf "%.1f", $2/1024}}' /proc/meminfo 2>/dev/null || echo 512)
  MEM_AVAIL=$(awk '/MemAvailable/ {{printf "%.1f", $2/1024}}' /proc/meminfo 2>/dev/null || echo 256)
  RAW_TEMP=$(cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null || echo 42000)
  TEMP_C=$(awk "BEGIN {{printf \\"%.1f\\", $RAW_TEMP / 1000}}")
  LAST_LOG=$(dmesg 2>/dev/null | tail -n 1 | tr -d '"\\\\' || echo "agent ok")

  PAYLOAD=$(cat <<EOF
{{"device_name":"$DEVICE_NAME","load_1m":$LOAD_1M,"load_5m":$LOAD_5M,"load_15m":$LOAD_15M,"mem_total_mb":$MEM_TOTAL,"cpu_temp_c":$TEMP_C,"uptime_seconds":$UPTIME,"logs":["$LAST_LOG"]}}
EOF
)
  if command -v curl >/dev/null 2>&1; then
    curl -s -X POST -H "Content-Type: application/json" -d "$PAYLOAD" "$SERVER_ENDPOINT" >/dev/null 2>&1
  elif command -v wget >/dev/null 2>&1; then
    wget -q -O - --header="Content-Type: application/json" --post-data="$PAYLOAD" "$SERVER_ENDPOINT" >/dev/null 2>&1
  fi
}}

if [ "$1" = "--once" ]; then
  send_heartbeat
  exit 0
fi

while true; do
  send_heartbeat
  sleep "$INTERVAL"
done
"""


class DAMFAgent:
    """Lightweight target-side heartbeat and telemetry reporter."""

    def __init__(
        self,
        server_url: str = "http://127.0.0.1:8080",
        device_name: str | None = None,
        board_type: str | None = None,
        interval: float = 15.0,
        log_lines: int = 20,
        app: Any = None,
    ):
        self.server_url = server_url.rstrip("/")
        self.device_name = device_name or socket.gethostname()
        self.board_type = board_type
        self.interval = float(interval)
        self.log_lines = int(log_lines)
        self._app = app

    def send_heartbeat(self, custom_telemetry: dict[str, Any] | None = None) -> dict[str, Any]:
        """Collect vital telemetry and push a single heartbeat to the DAMF server."""
        payload = custom_telemetry or collect_telemetry(
            device_name=self.device_name,
            board_type=self.board_type,
            log_lines=self.log_lines,
        )
        body = json.dumps(payload).encode("utf-8")
        if self._app is not None:
            status, _ctype, resp_bytes = self._app.handle_request("POST", "/api/v1/agent/heartbeat", body)
            if status >= 400:
                raise RuntimeError(f"Heartbeat rejected ({status}): {resp_bytes.decode('utf-8')}")
            return json.loads(resp_bytes.decode("utf-8"))

        url = f"{self.server_url}/api/v1/agent/heartbeat"
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10.0) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def run_forever(self, max_iterations: int | None = None) -> None:
        """Continuously push heartbeats every `self.interval` seconds."""
        count = 0
        while True:
            try:
                self.send_heartbeat()
            except (urllib.error.URLError, OSError, RuntimeError):
                pass
            count += 1
            if max_iterations is not None and count >= max_iterations:
                break
            time.sleep(self.interval)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="DAMF Target Heartbeat & Telemetry Agent")
    parser.add_argument("--server", default="http://127.0.0.1:8080", help="DAMF server URL")
    parser.add_argument("--name", default=socket.gethostname(), help="Device name in DAMF pool")
    parser.add_argument("--type", default="", help="Optional board_type")
    parser.add_argument("--interval", type=float, default=15.0, help="Heartbeat interval in seconds")
    parser.add_argument("--once", action="store_true", help="Send a single heartbeat and exit")
    parser.add_argument("--print-only", action="store_true", help="Print collected telemetry JSON to stdout and exit")
    args = parser.parse_args(argv)

    if args.print_only:
        print(json.dumps(collect_telemetry(device_name=args.name, board_type=args.type or None), indent=2))
        return 0

    agent = DAMFAgent(
        server_url=args.server,
        device_name=args.name,
        board_type=args.type or None,
        interval=args.interval,
    )
    if args.once:
        resp = agent.send_heartbeat()
        print(json.dumps(resp, indent=2))
        return 0

    agent.run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
