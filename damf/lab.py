"""Primary Python SDK entry point (`Lab` and `RemoteLabClient`) for test scripts."""

from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
from typing import Any, Iterator
import urllib.error
import urllib.parse
import urllib.request

from damf.config import load_config_file
from damf.device import Device
from damf.discovery import DiscoveryEngine
from damf.models import DeviceSpec, Reservation, TestSuiteResult
from damf.pool import ResourcePool
from damf.results import ResultParser


class Lab:
    """High-level DAMF interface for discovering, reserving, and automating lab devices.

    Example usage in a test script:
        from damf import Lab

        lab = Lab(seed_demo=True)
        with lab.acquire(board_type="raspberry-pi-4") as rpi:
            rpi.power_on()
            res = rpi.run("uname -a")
            assert res.ok
    """

    def __init__(
        self,
        db_path: str | Path = ":memory:",
        board_files_path: str | Path | None = None,
        seed_demo: bool = False,
    ):
        self.pool = ResourcePool(db_path=db_path, board_files_path=board_files_path)
        self.discovery = DiscoveryEngine()
        if seed_demo:
            self.pool.seed_demo_devices()

    def close(self) -> None:
        """Close the underlying ResourcePool database connection."""
        self.pool.close()

    @classmethod
    def from_config(cls, config_path: str | Path) -> "Lab":
        """Create a Lab instance populated from a YAML or JSON configuration file."""
        cfg = load_config_file(config_path)
        db_path = cfg.get("db_path", ":memory:")
        board_files = cfg.get("global_settings", {}).get("board_files_path")
        lab = cls(db_path=db_path, board_files_path=board_files)
        for dev_entry in cfg.get("devices", []):
            if isinstance(dev_entry, dict):
                lab.register_device(dev_entry)
        return lab

    @classmethod
    def discover(
        cls,
        db_path: str | Path = ":memory:",
        subnet_cidr: str | list[str] | None = None,
        include_arp: bool = True,
        include_mdns: bool = False,
        include_serial: bool = True,
        include_adb: bool = True,
    ) -> "Lab":
        """Create a Lab and immediately populate it by scanning the network/USB/ADB."""
        lab = cls(db_path=db_path)
        lab.scan_and_register(
            subnet_cidr=subnet_cidr,
            include_arp=include_arp,
            include_mdns=include_mdns,
            include_serial=include_serial,
            include_adb=include_adb,
        )
        return lab

    def register_device(self, spec: DeviceSpec | dict[str, Any], overwrite: bool = True) -> DeviceSpec:
        """Add or update a device in the lab pool and synchronize bidirectional topology links."""
        registered = self.pool.register_device(spec, overwrite=overwrite)
        for peer_name in registered.connected_to:
            peer = self.pool.get_device(peer_name)
            if peer is not None and registered.name not in peer.connected_to:
                peer.connected_to.append(registered.name)
                self.pool.register_device(peer, overwrite=True)
        return registered

    def define_device(
        self,
        name: str,
        board_type: str = "generic-linux",
        ip_address: str = "",
        subnet: str | None = None,
        arch: str = "arm64",
        transport: str = "ssh",
        ssh_user: str = "root",
        ssh_port: int = 22,
        identity_file: str | None = None,
        password: str | None = None,
        os_hint: str | None = None,
        connected_to: list[str] | None = None,
        tags: list[str] | None = None,
        simulated: bool = False,
        power_type: str = "ssh",
    ) -> DeviceSpec:
        """Manually define and register a device in the lab topology with SSH/connection settings."""
        if not subnet:
            subnet = ".".join(ip_address.split(".")[:3]) + ".0/24" if ip_address and "." in ip_address else "192.168.10.0/24"
        t_cfg: dict[str, Any] = {
            "user": ssh_user,
            "port": int(ssh_port),
            "simulated": bool(simulated),
        }
        if identity_file:
            t_cfg["identity_file"] = identity_file
        if password:
            t_cfg["password"] = password
        attrs: dict[str, Any] = {}
        if os_hint:
            attrs["os"] = os_hint

        spec = DeviceSpec(
            name=name,
            board_type=board_type,
            arch=arch,
            ip_address=ip_address,
            subnet=subnet,
            transport=transport,
            transport_config=t_cfg,
            power_type=power_type if not simulated else "simulated",
            power_state="on",
            tags=list(tags or []),
            attributes=attrs,
            connected_to=list(connected_to or []),
        )
        return self.register_device(spec, overwrite=True)

    def link_devices(self, device_a: str, device_b: str) -> dict[str, Any]:
        """Create a bidirectional topology link between two devices in the lab."""
        dev_a = self.pool.get_device(device_a)
        dev_b = self.pool.get_device(device_b)
        if dev_a is None:
            from damf.exceptions import DeviceNotFoundError

            raise DeviceNotFoundError(f"Device '{device_a}' not found")
        if dev_b is None:
            from damf.exceptions import DeviceNotFoundError

            raise DeviceNotFoundError(f"Device '{device_b}' not found")
        if device_b not in dev_a.connected_to:
            dev_a.connected_to.append(device_b)
            self.pool.register_device(dev_a, overwrite=True)
        if device_a not in dev_b.connected_to:
            dev_b.connected_to.append(device_a)
            self.pool.register_device(dev_b, overwrite=True)
        return {"source": device_a, "target": device_b, "linked": True}

    def unlink_devices(self, device_a: str, device_b: str) -> dict[str, Any]:
        """Remove a topology link between two devices in the lab."""
        dev_a = self.pool.get_device(device_a)
        dev_b = self.pool.get_device(device_b)
        if dev_a is not None and device_b in dev_a.connected_to:
            dev_a.connected_to = [p for p in dev_a.connected_to if p != device_b]
            self.pool.register_device(dev_a, overwrite=True)
        if dev_b is not None and device_a in dev_b.connected_to:
            dev_b.connected_to = [p for p in dev_b.connected_to if p != device_a]
            self.pool.register_device(dev_b, overwrite=True)
        return {"source": device_a, "target": device_b, "linked": False}

    def connect_ssh(self, name: str, verify_auth: bool = False) -> dict[str, Any]:
        """Connect to `name` over SSH, detect its running OS, and persist metadata to the pool."""
        dev = self.get_device(name)
        info = dev.connect_ssh(verify_auth=verify_auth)
        self.pool.register_device(dev.spec, overwrite=True)
        return info

    def reboot_device(self, name: str, via_ssh: bool = True, force_os_probe: bool = False) -> dict[str, Any]:
        """Reboot `name` (by default over SSH using OS-appropriate Linux/Unix reboot command)."""
        dev = self.get_device(name)
        res = dev.reboot(via_ssh=via_ssh, force_os_probe=force_os_probe)
        self.pool.register_device(dev.spec, overwrite=True)
        return {
            "device": dev.name,
            "power_state": dev.power_state,
            "os_info": dev.spec.attributes.get("os_info", {}),
            "reboot_command": res.command,
            "returncode": res.returncode,
            "stdout": res.stdout,
            "stderr": res.stderr,
        }

    def record_heartbeat(self, payload: dict[str, Any]) -> DeviceSpec:
        """Process an incoming heartbeat from a target agent and update device telemetry."""
        return self.pool.record_heartbeat(payload)

    def check_agent_health(self, timeout_seconds: float = 45.0) -> list[str]:
        """Mark agent-monitored boards as offline if they missed heartbeats for `timeout_seconds`."""
        return self.pool.mark_stale_agents_offline(timeout_seconds=timeout_seconds)

    def deploy_agent(
        self,
        name: str,
        server_url: str = "http://127.0.0.1:8080",
        interval: int = 15,
        prefer_shell: bool = False,
    ) -> dict[str, Any]:
        """Deploy and start the DAMF heartbeat/telemetry agent on `name` over SSH."""
        dev = self.get_device(name)
        info = dev.deploy_agent(server_url=server_url, interval=interval, prefer_shell=prefer_shell)
        self.pool.register_device(dev.spec, overwrite=True)
        return info

    def get_telemetry(self, name: str, refresh: bool = False, log_lines: int = 25) -> dict[str, Any]:
        """Get vital telemetry (CPU load, RAM, Temp, Uptime, System Logs) for `name`."""
        dev = self.get_device(name)
        info = dev.fetch_telemetry(refresh=refresh, log_lines=log_lines)
        self.pool.register_device(dev.spec, overwrite=True)
        return info

    def copy_system_logs(
        self,
        name: str,
        output_dir: str | Path | None = None,
        max_lines: int = 200,
        remote_files: list[str] | None = None,
    ) -> dict[str, Any]:
        """On-demand copy of system/kernel logs from target `name` to `output_dir` (and pool cache)."""
        dev = self.get_device(name)
        info = dev.copy_system_logs(output_dir=output_dir, max_lines=max_lines, remote_files=remote_files)
        self.pool.register_device(dev.spec, overwrite=True)
        return info

    def devices(
        self,
        board_type: str | None = None,
        arch: str | None = None,
        state: str | None = None,
        tags: list[str] | None = None,
    ) -> list[DeviceSpec]:
        """List devices in the lab pool matching the given filters."""
        return self.pool.list_devices(board_type=board_type, arch=arch, state=state, tags=tags)

    def get_device(self, name: str) -> Device:
        """Get a `Device` wrapper for a specific device name without reserving it."""
        spec = self.pool.get_device(name)
        if spec is None:
            from damf.exceptions import DeviceNotFoundError

            raise DeviceNotFoundError(f"Device '{name}' not found in lab")
        return Device(spec=spec)

    def scan_and_register(
        self,
        subnet_cidr: str | list[str] | None = None,
        include_arp: bool = True,
        include_mdns: bool = False,
        include_serial: bool = True,
        include_adb: bool = True,
        only_known_arp_vendors: bool = False,
    ) -> list[DeviceSpec]:
        """Run network and local bus discovery and register all discovered boards."""
        found = self.discovery.discover_all(
            include_arp=include_arp,
            include_mdns=include_mdns,
            include_serial=include_serial,
            include_adb=include_adb,
            subnet_cidr=subnet_cidr,
            only_known_arp_vendors=only_known_arp_vendors,
        )
        for spec in found:
            self.pool.register_device(spec, overwrite=False)
        return found

    def acquire(
        self,
        name: str | None = None,
        board_type: str | None = None,
        arch: str | None = None,
        tags: list[str] | None = None,
        owner: str = "pytest",
        ttl_seconds: float = 1800.0,
        purpose: str = "automated-test",
        auto_connect: bool = True,
    ) -> Device:
        """Reserve a matching device and return a `Device` context manager.

        When used in a `with` block, the device reservation is automatically released on exit.
        """
        spec, reservation = self.pool.reserve(
            name=name,
            board_type=board_type,
            arch=arch,
            tags=tags,
            owner=owner,
            ttl_seconds=ttl_seconds,
            purpose=purpose,
        )

        def _release_cb(dev: Device) -> None:
            self.pool.release(dev.name, reservation_id=reservation.reservation_id, force=True)

        device = Device(spec=spec, on_release=_release_cb)
        if auto_connect:
            device.connect()
        return device

    @contextmanager
    def acquire_cluster(
        self,
        role_requirements: dict[str, dict[str, Any]],
        owner: str = "pytest",
        ttl_seconds: float = 1800.0,
        auto_connect: bool = True,
    ) -> Iterator[dict[str, Device]]:
        """Atomically acquire multiple devices by role (e.g. {'master': {'board_type': 'rpi4'}, 'slave': {...}})."""
        acquired: dict[str, Device] = {}
        try:
            for role, req in role_requirements.items():
                acquired[role] = self.acquire(
                    name=req.get("name"),
                    board_type=req.get("board_type"),
                    arch=req.get("arch"),
                    tags=req.get("tags"),
                    owner=owner,
                    ttl_seconds=ttl_seconds,
                    purpose=f"cluster:{role}",
                    auto_connect=auto_connect,
                )
            yield acquired
        finally:
            for dev in list(acquired.values()):
                try:
                    dev.release()
                except Exception:
                    pass

    def run_test_suite(
        self,
        device: Device,
        commands: dict[str, str] | list[str],
        suite_name: str = "default",
        owner: str = "admin",
        output_dir: str | Path | None = None,
    ) -> TestSuiteResult:
        """Execute a test suite on `device`, record the job in `ResourcePool`, and optionally export JUnit XML."""
        suite = device.run_test_commands(commands, suite_name=suite_name)
        status = "PASS" if suite.failed == 0 else "FAIL"
        self.pool.record_test_job(
            device_name=device.name,
            suite_name=suite_name,
            status=status,
            owner=owner,
            passed=suite.passed,
            failed=suite.failed,
            skipped=suite.skipped,
            details=suite.to_dict(),
        )
        if output_dir is not None:
            parser = ResultParser(output_dir, output_dir)
            parser.write_junit_xml(suite, suite_name)
            parser.write_json_report(suite)
        return suite

    def topology(self) -> dict[str, Any]:
        """Build a network/subnet and peer-relationship graph of all devices in the lab."""
        devices = self.pool.list_devices()
        subnets: dict[str, list[dict[str, Any]]] = {}
        links: list[dict[str, str]] = []
        seen_links: set[tuple[str, str]] = set()

        for dev in devices:
            sub = dev.subnet or "local-bus"
            subnets.setdefault(sub, []).append(dev.to_dict())
            for peer in dev.connected_to:
                pair = tuple(sorted((dev.name, peer)))
                if pair not in seen_links:
                    seen_links.add(pair)
                    links.append({"source": dev.name, "target": peer})

        return {
            "subnets": subnets,
            "devices": [d.to_dict() for d in devices],
            "links": links,
        }


class RemoteLabClient:
    """HTTP REST client allowing Python test scripts to interact with a DAMF server."""

    def __init__(self, base_url: str = "http://127.0.0.1:8080", app: Any = None):
        self.base_url = base_url.rstrip("/")
        self._app = app

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> Any:
        body = json.dumps(payload).encode("utf-8") if payload is not None else b""
        if self._app is not None:
            status, _ctype, resp_bytes = self._app.handle_request(method, path, body)
            data = json.loads(resp_bytes.decode("utf-8"))
            if status >= 400:
                raise RuntimeError(f"API error {status}: {data}")
            return data

        url = f"{self.base_url}{path}"
        headers = {"Content-Type": "application/json"} if payload is not None else {}
        req = urllib.request.Request(url, data=body if payload is not None else None, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=15.0) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def status(self) -> dict[str, Any]:
        return self._request("GET", "/api/v1/status")

    def list_devices(self, **filters: str) -> list[dict[str, Any]]:
        query = urllib.parse.urlencode({k: v for k, v in filters.items() if v})
        suffix = f"?{query}" if query else ""
        return self._request("GET", f"/api/v1/devices{suffix}")["devices"]

    def reserve(self, name: str, owner: str = "remote-script", ttl_seconds: float = 1800.0) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/api/v1/devices/{urllib.parse.quote(name)}/reserve",
            {"owner": owner, "ttl_seconds": ttl_seconds},
        )

    def release(self, name: str) -> dict[str, Any]:
        return self._request("POST", f"/api/v1/devices/{urllib.parse.quote(name)}/release", {})

    def run_command(self, name: str, command: str) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/api/v1/devices/{urllib.parse.quote(name)}/exec",
            {"command": command},
        )

    def add_device(self, **device_fields: Any) -> dict[str, Any]:
        """Define/create a new device in the remote lab topology."""
        return self._request("POST", "/api/v1/devices", device_fields)

    def link_devices(self, source: str, target: str) -> dict[str, Any]:
        """Create a topology link between two devices on the remote server."""
        return self._request("POST", "/api/v1/topology/links", {"source": source, "target": target})

    def connect_ssh(self, name: str, verify_auth: bool = False) -> dict[str, Any]:
        """Connect via SSH to the specified target and detect its OS."""
        return self._request(
            "POST",
            f"/api/v1/devices/{urllib.parse.quote(name)}/connect",
            {"verify_auth": verify_auth},
        )

    def reboot(self, name: str, via_ssh: bool = True) -> dict[str, Any]:
        """Trigger a context-aware Linux/Unix SSH reboot on the specified target."""
        return self._request(
            "POST",
            f"/api/v1/devices/{urllib.parse.quote(name)}/reboot",
            {"via_ssh": via_ssh},
        )

    def send_heartbeat(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Send an agent heartbeat payload to `/api/v1/agent/heartbeat`."""
        return self._request("POST", "/api/v1/agent/heartbeat", payload)

    def deploy_agent(
        self,
        name: str,
        server_url: str = "http://127.0.0.1:8080",
        interval: int = 15,
        prefer_shell: bool = False,
    ) -> dict[str, Any]:
        """Deploy the target heartbeat agent over SSH via the REST API."""
        return self._request(
            "POST",
            f"/api/v1/devices/{urllib.parse.quote(name)}/deploy-agent",
            {"server_url": server_url, "interval": interval, "prefer_shell": prefer_shell},
        )

    def get_telemetry(self, name: str, refresh: bool = False) -> dict[str, Any]:
        """Fetch vital load, memory, temperature, and system logs for `name`."""
        suffix = "?refresh=1" if refresh else ""
        return self._request("GET", f"/api/v1/devices/{urllib.parse.quote(name)}/telemetry{suffix}")

    def copy_system_logs(
        self,
        name: str,
        output_dir: str | Path | None = None,
        max_lines: int = 200,
        remote_files: list[str] | None = None,
    ) -> dict[str, Any]:
        """Request on-demand system log collection from target `name` via the REST API and optionally save locally."""
        resp = self._request(
            "POST",
            f"/api/v1/devices/{urllib.parse.quote(name)}/logs",
            {
                "max_lines": max_lines,
                "remote_files": remote_files or [],
                "output_dir": str(output_dir) if output_dir else None,
            },
        )
        if output_dir is not None and not resp.get("saved_path"):
            out_dir = Path(output_dir)
            out_dir.mkdir(parents=True, exist_ok=True)
            out_file = out_dir / f"{name}_system_logs.log"
            out_file.write_text(resp.get("combined_text", ""), encoding="utf-8")
            resp["saved_path"] = str(out_file)
        return resp
