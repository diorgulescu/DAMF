"""REST API router, WSGI application, and standalone HTTP server for DAMF."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from typing import Any
import urllib.parse

from damf.config import dump_yaml
from damf.exceptions import DAMFError, DeviceBusyError, DeviceNotFoundError
from damf.lab import Lab
from damf.models import DeviceSpec
from damf.web.ui_html import DASHBOARD_HTML


class DAMFWebApp:
    """Framework-agnostic REST API & UI router for DAMF.

    Can be served directly by `ThreadingHTTPServer`, mounted as a WSGI app,
    or delegated to from Flask routes.
    """

    def __init__(self, lab: Lab | None = None):
        self.lab = lab or Lab(seed_demo=True)

    def _register_from_payload(self, payload: dict[str, Any]) -> DeviceSpec:
        """Normalize a REST device creation/update payload and register it in the lab topology."""
        if any(k in payload for k in ("ssh_user", "ssh_port", "identity_file", "password", "os_hint")):
            return self.lab.define_device(
                name=str(payload["name"]),
                board_type=str(payload.get("board_type", "generic-linux")),
                ip_address=str(payload.get("ip_address", "")),
                subnet=payload.get("subnet"),
                arch=str(payload.get("arch", "arm64")),
                transport=str(payload.get("transport", "ssh")),
                ssh_user=str(payload.get("ssh_user", "root")),
                ssh_port=int(payload.get("ssh_port", 22)),
                identity_file=payload.get("identity_file") or None,
                password=payload.get("password") or None,
                os_hint=payload.get("os_hint") or None,
                connected_to=payload.get("connected_to") or [],
                tags=payload.get("tags") or [],
                simulated=bool(payload.get("simulated", False)),
                power_type=str(payload.get("power_type", "ssh")),
            )
        return self.lab.register_device(payload, overwrite=True)

    def handle_request(
        self,
        method: str,
        raw_path: str,
        body: bytes = b"",
    ) -> tuple[int, str, bytes]:
        """Dispatch an HTTP request and return (status_code, content_type, response_bytes)."""
        parsed = urllib.parse.urlparse(raw_path)
        path = parsed.path.rstrip("/") or "/"
        query = dict(urllib.parse.parse_qsl(parsed.query))

        def json_resp(data: Any, status: int = 200) -> tuple[int, str, bytes]:
            return status, "application/json; charset=utf-8", json.dumps(data, indent=2).encode("utf-8")

        def html_resp(html: str, status: int = 200) -> tuple[int, str, bytes]:
            return status, "text/html; charset=utf-8", html.encode("utf-8")

        payload: dict[str, Any] = {}
        if body:
            try:
                payload = json.loads(body.decode("utf-8"))
            except ValueError:
                payload = {}

        try:
            # UI Routes
            if method == "GET" and path in (
                "/",
                "/index",
                "/index.html",
                "/devices",
                "/lab",
                "/dashboard",
                "/setup",
                "/reports",
                "/administration",
            ):
                return html_resp(DASHBOARD_HTML)

            # API v1: Status
            if method == "GET" and path == "/api/v1/status":
                all_devs = self.lab.devices()
                avail = [d for d in all_devs if d.state == "available"]
                reserved = [d for d in all_devs if d.state == "reserved"]
                jobs = self.lab.pool.list_test_jobs()
                return json_resp(
                    {
                        "total_devices": len(all_devs),
                        "available_devices": len(avail),
                        "reserved_devices": len(reserved),
                        "total_jobs": len(jobs),
                        "board_types": self.lab.pool.board_types,
                    }
                )

            # API v1: Agent Heartbeat & Health Check
            if method == "POST" and path == "/api/v1/agent/heartbeat":
                spec = self.lab.record_heartbeat(payload)
                return json_resp(
                    {
                        "ack": True,
                        "device": spec.name,
                        "state": spec.state,
                        "last_seen": spec.last_seen,
                    }
                )

            if method == "POST" and path == "/api/v1/agent/check-health":
                timeout_sec = float(payload.get("timeout_seconds", 45.0))
                marked = self.lab.check_agent_health(timeout_seconds=timeout_sec)
                return json_resp({"marked_offline": marked})

            # API v1: Topology & Links
            if method == "GET" and path == "/api/v1/topology":
                return json_resp(self.lab.topology())

            if method == "POST" and path == "/api/v1/topology/devices":
                spec = self._register_from_payload(payload)
                return json_resp(spec.to_dict(), status=201)

            if path == "/api/v1/topology/links":
                src = str(payload.get("source", ""))
                dst = str(payload.get("target", ""))
                if method == "POST":
                    return json_resp(self.lab.link_devices(src, dst), status=201)
                if method == "DELETE":
                    return json_resp(self.lab.unlink_devices(src, dst))

            # API v1: Settings
            if path == "/api/v1/settings":
                if method == "GET":
                    return json_resp(self.lab.pool.get_settings())
                if method in ("POST", "PUT"):
                    return json_resp(self.lab.pool.update_settings(payload))

            # API v1: Discovery
            if method == "POST" and path == "/api/v1/discover":
                found = self.lab.scan_and_register(
                    subnet_cidr=payload.get("subnet_cidr"),
                    include_arp=bool(payload.get("include_arp", True)),
                    include_mdns=bool(payload.get("include_mdns", False)),
                    include_serial=bool(payload.get("include_serial", True)),
                    include_adb=bool(payload.get("include_adb", True)),
                    only_known_arp_vendors=bool(payload.get("only_known_arp_vendors", True)),
                )
                return json_resp(
                    {
                        "discovered_count": len(found),
                        "discovered": [d.to_dict() for d in found],
                    }
                )

            # API v1: Jobs
            if path == "/api/v1/jobs":
                if method == "GET":
                    return json_resp({"jobs": self.lab.pool.list_test_jobs(owner=query.get("owner"))})
                if method == "POST":
                    dev_name = payload.get("device_name")
                    commands = payload.get("commands", ["uname -a"])
                    suite_name = payload.get("suite_name", "api-suite")
                    owner = payload.get("owner", "api-user")
                    device = self.lab.get_device(dev_name)
                    suite = self.lab.run_test_suite(device, commands=commands, suite_name=suite_name, owner=owner)
                    return json_resp(suite.to_dict(), status=201)

            # API v1: Devices collection
            if path == "/api/v1/devices":
                if method == "GET":
                    tags = [query["tag"]] if "tag" in query else None
                    devs = self.lab.devices(
                        board_type=query.get("board_type"),
                        arch=query.get("arch"),
                        state=query.get("state"),
                        tags=tags,
                    )
                    return json_resp({"devices": [d.to_dict() for d in devs]})
                if method == "POST":
                    spec = self._register_from_payload(payload)
                    return json_resp(spec.to_dict(), status=201)

            # API v1: Single device & sub-actions
            if path.startswith("/api/v1/devices/"):
                parts = [urllib.parse.unquote(p) for p in path.split("/")[4:]]
                dev_name = parts[0]
                action = parts[1] if len(parts) > 1 else None

                if action is None:
                    if method == "GET":
                        spec = self.lab.pool.get_device(dev_name)
                        if spec is None:
                            raise DeviceNotFoundError(f"Device '{dev_name}' not found")
                        return json_resp(spec.to_dict())
                    if method == "PUT":
                        existing = self.lab.pool.get_device(dev_name)
                        if existing is None:
                            raise DeviceNotFoundError(f"Device '{dev_name}' not found")
                        merged = {**existing.to_dict(), **payload, "name": dev_name}
                        updated = self.lab.register_device(DeviceSpec.from_dict(merged), overwrite=True)
                        return json_resp(updated.to_dict())
                    if method == "DELETE":
                        removed = self.lab.pool.remove_device(dev_name)
                        if not removed:
                            raise DeviceNotFoundError(f"Device '{dev_name}' not found")
                        return json_resp({"deleted": dev_name})

                elif action == "export" and method == "GET":
                    spec = self.lab.pool.get_device(dev_name)
                    if spec is None:
                        raise DeviceNotFoundError(f"Device '{dev_name}' not found")
                    fmt = query.get("format", "yaml").lower()
                    if fmt == "json":
                        return json_resp(spec.to_dict())
                    yaml_bytes = dump_yaml(spec.to_dict()).encode("utf-8")
                    return 200, "text/yaml; charset=utf-8", yaml_bytes

                elif action == "reserve" and method == "POST":
                    spec, res = self.lab.pool.reserve(
                        name=dev_name,
                        owner=str(payload.get("owner", "api-user")),
                        ttl_seconds=float(payload.get("ttl_seconds", 1800.0)),
                        purpose=str(payload.get("purpose", "api")),
                    )
                    return json_resp({"device": spec.to_dict(), "reservation": res.to_dict()})

                elif action == "release" and method == "POST":
                    self.lab.pool.release(dev_name, reservation_id=payload.get("reservation_id"), force=True)
                    spec = self.lab.pool.get_device(dev_name)
                    return json_resp({"released": dev_name, "device": spec.to_dict() if spec else None})

                elif action == "connect" and method == "POST":
                    verify_auth = bool(payload.get("verify_auth", False))
                    info = self.lab.connect_ssh(dev_name, verify_auth=verify_auth)
                    return json_resp(info)

                elif action == "deploy-agent" and method == "POST":
                    server_url = str(payload.get("server_url", "http://127.0.0.1:8080"))
                    interval = int(payload.get("interval", 15))
                    prefer_shell = bool(payload.get("prefer_shell", False))
                    info = self.lab.deploy_agent(
                        dev_name,
                        server_url=server_url,
                        interval=interval,
                        prefer_shell=prefer_shell,
                    )
                    return json_resp(info)

                elif action == "telemetry" and method == "GET":
                    refresh = query.get("refresh", "").lower() in ("1", "true", "yes")
                    lines = int(query.get("lines", "25"))
                    info = self.lab.get_telemetry(dev_name, refresh=refresh, log_lines=lines)
                    return json_resp(info)

                elif action == "reboot" and method == "POST":
                    via_ssh = bool(payload.get("via_ssh", True))
                    force_os = bool(payload.get("force_os_probe", False))
                    info = self.lab.reboot_device(dev_name, via_ssh=via_ssh, force_os_probe=force_os)
                    return json_resp(info)

                elif action == "power" and method == "POST":
                    dev = self.lab.get_device(dev_name)
                    pwr_action = str(payload.get("action", "on")).lower()
                    if pwr_action in ("reboot", "reset", "cycle"):
                        info = self.lab.reboot_device(dev_name, via_ssh=bool(payload.get("via_ssh", True)))
                        return json_resp(info)
                    if pwr_action == "on":
                        dev.power_on()
                    elif pwr_action == "off":
                        dev.power_off()
                    self.lab.register_device(dev.spec, overwrite=True)
                    return json_resp({"device": dev.name, "power_state": dev.power_state})

                elif action == "exec" and method == "POST":
                    dev = self.lab.get_device(dev_name)
                    cmd = str(payload.get("command", "uname -a"))
                    res = dev.run(cmd)
                    return json_resp(
                        {
                            "device": dev.name,
                            "command": res.command,
                            "returncode": res.returncode,
                            "stdout": res.stdout,
                            "stderr": res.stderr,
                            "duration_sec": res.duration_sec,
                        }
                    )

            return json_resp({"error": f"Route not found: {method} {path}"}, status=404)

        except DeviceNotFoundError as exc:
            return json_resp({"error": str(exc)}, status=404)
        except DeviceBusyError as exc:
            return json_resp({"error": str(exc)}, status=409)
        except DAMFError as exc:
            return json_resp({"error": str(exc)}, status=400)


def create_http_server(
    host: str = "127.0.0.1",
    port: int = 8080,
    lab: Lab | None = None,
) -> ThreadingHTTPServer:
    """Create a ThreadingHTTPServer serving the DAMF Web UI and REST API."""
    web_app = DAMFWebApp(lab=lab)

    class Handler(BaseHTTPRequestHandler):
        def _dispatch(self, method: str) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length) if length > 0 else b""
            status, content_type, data = web_app.handle_request(method, self.path, body)
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:
            self._dispatch("GET")

        def do_POST(self) -> None:
            self._dispatch("POST")

        def do_PUT(self) -> None:
            self._dispatch("PUT")

        def do_DELETE(self) -> None:
            self._dispatch("DELETE")

        def log_message(self, format: str, *args: Any) -> None:
            pass

    server = ThreadingHTTPServer((host, port), Handler)
    server.damf_app = web_app  # type: ignore[attr-defined]
    return server
