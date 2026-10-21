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

            # API v1: Topology
            if method == "GET" and path == "/api/v1/topology":
                return json_resp(self.lab.topology())

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
                    spec = self.lab.register_device(payload, overwrite=True)
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

                elif action == "power" and method == "POST":
                    dev = self.lab.get_device(dev_name)
                    pwr_action = str(payload.get("action", "on")).lower()
                    if pwr_action == "on":
                        dev.power_on()
                    elif pwr_action == "off":
                        dev.power_off()
                    elif pwr_action in ("reboot", "reset", "cycle"):
                        dev.reboot(delay_sec=0.05)
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
