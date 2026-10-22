"""High-level Device API combining metadata, transport, power control, and bootloader workflows."""

from __future__ import annotations

import logging
from pathlib import Path
import time
from typing import Any, Callable

from damf.exceptions import TransportError
from damf.models import CommandResult, DeviceSpec, TestCaseResult, TestSuiteResult
from damf.power import PowerController, create_power_controller
from damf.transports import (
    SerialTransport,
    SSHTransport,
    Transport,
    create_transport,
    determine_reboot_command,
    parse_os_probe_output,
)


class Device:
    """High-level handle to a lab device or development board.

    Can be used directly or as a context manager returned by `lab.acquire(...)`.
    """

    def __init__(
        self,
        spec: DeviceSpec,
        transport: Transport | None = None,
        power: PowerController | None = None,
        on_release: Callable[["Device"], None] | None = None,
    ):
        self.spec = spec
        self.transport: Transport = transport or create_transport(spec)
        self.power: PowerController = power or create_power_controller(spec)
        self._on_release = on_release
        self.logger = logging.getLogger(f"damf.device.{spec.name}")

    # Convenient property accessors
    @property
    def name(self) -> str:
        return self.spec.name

    @property
    def board_type(self) -> str:
        return self.spec.board_type

    @property
    def arch(self) -> str:
        return self.spec.arch

    @property
    def ip(self) -> str:
        return self.spec.ip_address

    @property
    def state(self) -> str:
        return self.spec.state

    @property
    def power_state(self) -> str:
        return self.spec.power_state

    # Lifecycle & Context Manager
    def connect(self) -> "Device":
        """Connect to the target over its configured transport."""
        self.transport.connect()
        return self

    def connect_ssh(self, verify_auth: bool = False) -> dict[str, Any]:
        """Connect to the target over SSH, detect its running OS, and return connection details."""
        ssh = self.transport if isinstance(self.transport, SSHTransport) else SSHTransport(self.spec)
        ssh.connect(verify_auth=verify_auth)
        self.transport.connected = True
        os_info = ssh.detect_os(force_refresh=True)
        return {
            "device": self.name,
            "connected": True,
            "host": ssh.host,
            "port": ssh.port,
            "user": ssh.user,
            "ssh_banner": self.spec.attributes.get("ssh_banner", ""),
            "os_info": os_info,
            "interactive_cmd": " ".join(ssh.build_interactive_ssh_command()),
        }

    def detect_os(self, force_refresh: bool = False) -> dict[str, str]:
        """Detect the OS, distribution, and init system running on the target."""
        if isinstance(self.transport, SSHTransport):
            return self.transport.detect_os(force_refresh=force_refresh)
        if not force_refresh and isinstance(self.spec.attributes.get("os_info"), dict):
            return dict(self.spec.attributes["os_info"])

        probe_script = (
            "echo __DAMF_KERNEL__; uname -s 2>/dev/null || true; "
            "echo __DAMF_ARCH__; uname -m 2>/dev/null || true; "
            "echo __DAMF_OS_RELEASE__; cat /etc/os-release 2>/dev/null || true; "
            "echo __DAMF_INIT__; ps -p 1 -o comm= 2>/dev/null || true"
        )
        res = self.run(probe_script, timeout=10.0)
        fallback = f"{self.spec.attributes.get('os', '')} {self.spec.deployed_image} {self.spec.board_type}".strip()
        os_info = parse_os_probe_output(res.stdout if res.ok else "", fallback_hint=fallback)
        user = str(self.spec.transport_config.get("user", "root"))
        os_info["reboot_command"] = determine_reboot_command(os_info, user=user)
        self.spec.attributes["os_info"] = os_info
        return os_info

    def disconnect(self) -> None:
        """Close the transport connection."""
        self.transport.disconnect()

    def release(self) -> None:
        """Disconnect and invoke the ResourcePool release callback if present."""
        self.disconnect()
        if self._on_release is not None:
            cb = self._on_release
            self._on_release = None
            cb(self)

    def __enter__(self) -> "Device":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.release()

    # Power & Boot Operations
    def power_on(self) -> None:
        """Power on the device."""
        self.logger.info("Powering on %s", self.name)
        self.power.power_on()

    def power_off(self) -> None:
        """Power off the device."""
        self.logger.info("Powering off %s", self.name)
        self.power.power_off()

    def reboot(
        self,
        delay_sec: float = 0.2,
        via_ssh: bool | None = None,
        force_os_probe: bool = False,
    ) -> CommandResult:
        """Reboot the device.

        By default, for SSH-capable targets (or when `via_ssh=True`), detects the running
        Linux/Unix OS over SSH and issues the appropriate OS-specific reboot command.
        """
        self.logger.info("Rebooting %s", self.name)
        use_ssh = via_ssh if via_ssh is not None else (
            isinstance(self.transport, SSHTransport)
            or self.spec.power_type == "ssh"
            or (bool(self.spec.ip_address) and self.spec.transport in ("ssh", "serial"))
        )
        if use_ssh:
            ssh = self.transport if isinstance(self.transport, SSHTransport) else SSHTransport(self.spec)
            res = ssh.reboot_over_ssh(force_os_probe=force_os_probe)
            self.spec.power_state = "on"
            return res

        self.power.reboot(delay_sec=delay_sec)
        return CommandResult(
            command="power_controller.reboot",
            returncode=0,
            stdout=f"Power cycled {self.name}\n",
            device_name=self.name,
        )

    def reset(self) -> None:
        """Alias for reboot()."""
        self.reboot()

    def boot_bootloader(
        self,
        boot_method: str = "ramdisk",
        params: dict[str, str] | None = None,
    ) -> list[str]:
        """Execute bootloader (e.g., U-Boot) commands for ramdisk or NFS boot."""
        raw_commands = (
            self.spec.boot_commands.get(f"{boot_method}_boot")
            or self.spec.boot_commands.get(boot_method)
            or []
        )
        if not raw_commands:
            return []

        replacements = params or {}
        if isinstance(self.transport, SerialTransport):
            return self.transport.send_uboot_commands(raw_commands, replacements)

        rendered: list[str] = []
        for cmd in raw_commands:
            line = cmd
            for k, v in replacements.items():
                line = line.replace(f"{{{k.upper()}}}", str(v))
            rendered.append(line)
        return rendered

    # Command Execution & File Transfers
    def run(
        self,
        command: str,
        timeout: float = 60.0,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        check: bool = False,
    ) -> CommandResult:
        """Execute a command on the device over its active transport."""
        result = self.transport.run(command, timeout=timeout, env=env, cwd=cwd)
        if check:
            result.check()
        return result

    def upload(self, local_path: str | Path, remote_path: str) -> None:
        """Upload a local file or directory to the device."""
        self.transport.upload(local_path, remote_path)

    def download(self, remote_path: str, local_path: str | Path) -> None:
        """Download a file or directory from the device to the local machine."""
        self.transport.download(remote_path, local_path)

    def is_alive(self) -> bool:
        """Return True if the device responds over its transport."""
        return self.transport.is_alive()

    def wait_until_online(self, timeout: float = 60.0, interval: float = 1.0) -> bool:
        """Poll `is_alive()` until the device responds or `timeout` elapses."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.is_alive():
                return True
            time.sleep(interval)
        raise TransportError(f"Device '{self.name}' did not come online within {timeout}s")

    def run_test_commands(
        self,
        commands: dict[str, str] | list[str],
        suite_name: str = "default",
        env: dict[str, str] | None = None,
    ) -> TestSuiteResult:
        """Run a batch of test commands on the device and collect structured results."""
        suite = TestSuiteResult(suite_name=suite_name, device_name=self.name)
        items = commands.items() if isinstance(commands, dict) else [(cmd, cmd) for cmd in commands]
        for test_name, cmd in items:
            res = self.run(cmd, env=env)
            status = "PASS" if res.ok else "FAIL"
            suite.cases.append(
                TestCaseResult(
                    name=str(test_name),
                    status=status,
                    duration_sec=res.duration_sec,
                    stdout=res.stdout,
                    message=res.stderr if not res.ok else "",
                )
            )
        return suite

    def deploy_agent(
        self,
        server_url: str = "http://127.0.0.1:8080",
        interval: int = 15,
        prefer_shell: bool = False,
    ) -> dict[str, Any]:
        """Deploy and start the DAMF heartbeat/telemetry agent on this target over SSH/transport.

        Automatically chooses Tier-1 (`damf/agent.py` stdlib Python) when `python3` is present on
        the target, or falls back to Tier-2 (`damf-agent.sh` POSIX/BusyBox shell script).
        """
        from damf.agent import collect_telemetry, generate_posix_shell_agent
        import tempfile

        self.connect()
        has_python3 = False
        if not prefer_shell:
            if self.spec.transport_config.get("simulated", False):
                has_python3 = "busybox" not in str(self.spec.attributes.get("os", "")).lower()
            else:
                probe = self.run("command -v python3 >/dev/null 2>&1 && echo PY3_OK || echo NO_PY3", timeout=10.0)
                has_python3 = "PY3_OK" in probe.stdout

        if has_python3:
            tier = "python"
            remote_script = "/tmp/damf_agent.py"
            local_agent = Path(__file__).parent / "agent.py"
            self.upload(local_agent, remote_script)
            start_cmd = (
                f"chmod +x {remote_script}; "
                f"nohup python3 {remote_script} --server {server_url} --name {self.name} "
                f"--interval {int(interval)} >/tmp/damf-agent.log 2>&1 &"
            )
            self.run(start_cmd, timeout=10.0)
        else:
            tier = "posix-sh"
            remote_script = "/tmp/damf_agent.sh"
            sh_content = generate_posix_shell_agent(server_url=server_url, device_name=self.name, interval=interval)
            with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False, encoding="utf-8") as tmp:
                tmp.write(sh_content)
                tmp_path = Path(tmp.name)
            try:
                self.upload(tmp_path, remote_script)
            finally:
                tmp_path.unlink(missing_ok=True)
            start_cmd = f"chmod +x {remote_script}; nohup sh {remote_script} >/tmp/damf-agent.log 2>&1 &"
            self.run(start_cmd, timeout=10.0)

        self.spec.attributes["agent_active"] = True
        self.spec.attributes["agent_tier"] = tier
        self.spec.attributes["agent_server_url"] = server_url
        if "telemetry" not in self.spec.attributes:
            snap = collect_telemetry(device_name=self.name, board_type=self.board_type)
            self.spec.attributes["telemetry"] = snap
        self.spec.last_seen = time.time()
        return {
            "device": self.name,
            "deployed": True,
            "agent_tier": tier,
            "remote_script": remote_script,
            "interval": int(interval),
            "server_url": server_url,
        }

    def fetch_telemetry(self, refresh: bool = False, log_lines: int = 25) -> dict[str, Any]:
        """Return vital telemetry and system logs (from latest agent heartbeat or live SSH query)."""
        from damf.agent import collect_telemetry

        cached = self.spec.attributes.get("telemetry")
        if cached and not refresh:
            age = round(max(0.0, time.time() - float(cached.get("heartbeat_at", self.spec.last_seen or time.time()))), 1)
            return {
                "device": self.name,
                "agent_active": bool(self.spec.attributes.get("agent_active", False)),
                "agent_tier": self.spec.attributes.get("agent_tier", "python"),
                "heartbeat_age_sec": age,
                **cached,
            }

        if self.spec.transport_config.get("simulated", False):
            snap = collect_telemetry(device_name=self.name, board_type=self.board_type, log_lines=log_lines)
        else:
            cmd = (
                "awk '{print $1, $2, $3}' /proc/loadavg 2>/dev/null || echo '0.1 0.1 0.1'; "
                "echo __DAMF_LOGS__; "
                f"(dmesg 2>/dev/null | tail -n {int(log_lines)}) || echo 'no logs'"
            )
            res = self.run(cmd, timeout=10.0)
            parts = res.stdout.split("__DAMF_LOGS__")
            loads = parts[0].strip().split() if parts and parts[0].strip() else ["0.0", "0.0", "0.0"]
            logs = parts[1].strip().splitlines() if len(parts) > 1 else []
            snap = collect_telemetry(device_name=self.name, board_type=self.board_type, log_lines=log_lines)
            try:
                snap["load_1m"] = float(loads[0])
                snap["load_5m"] = float(loads[1])
                snap["load_15m"] = float(loads[2])
            except (ValueError, IndexError):
                pass
            if logs:
                snap["logs"] = logs

        snap["heartbeat_at"] = time.time()
        self.spec.attributes["telemetry"] = snap
        self.spec.last_seen = snap["heartbeat_at"]
        return {
            "device": self.name,
            "agent_active": bool(self.spec.attributes.get("agent_active", False)),
            "agent_tier": self.spec.attributes.get("agent_tier", "ssh-live"),
            "heartbeat_age_sec": 0.0,
            **snap,
        }

    def copy_system_logs(
        self,
        output_dir: str | Path | None = None,
        max_lines: int = 200,
        remote_files: list[str] | None = None,
    ) -> dict[str, Any]:
        """Copy system and kernel logs on demand from the target to the host.

        Collects `dmesg`, `journalctl`, `/var/log/syslog`, `/var/log/messages` (or `logcat`
        on Android targets), optionally copies explicit `remote_files` via SCP/ADB/Serial,
        and writes a consolidated log bundle file when `output_dir` is specified.
        """
        now = time.time()
        ts_str = time.strftime("%Y%m%d_%H%M%S", time.localtime(now))
        sources: dict[str, str] = {}
        copied_files: list[str] = []

        if self.spec.transport_config.get("simulated", False):
            tel_logs = (self.spec.attributes.get("telemetry") or {}).get("logs") or [
                f"[00:00:01] kernel: Linux version 6.6.20 on {self.name} ({self.arch})",
                f"[00:00:03] systemd[1]: Reached target Multi-User System on {self.name}.",
            ]
            sources["dmesg"] = "\n".join(tel_logs)
            if self.spec.transport == "adb":
                sources["logcat"] = f"I/ActivityManager: Simulated Android logcat on {self.name}"
            else:
                sources["syslog"] = (
                    f"{time.strftime('%b %d %H:%M:%S')} {self.name} kernel: eth0 link up\n"
                    f"{time.strftime('%b %d %H:%M:%S')} {self.name} sshd: Accepted key for "
                    f"{self.spec.transport_config.get('user', 'root')}"
                )
        elif self.spec.transport == "adb":
            lc = self.run(f"logcat -d -t {int(max_lines)}", timeout=15.0)
            dm = self.run(f"dmesg | tail -n {int(max_lines)}", timeout=15.0)
            if lc.stdout.strip():
                sources["logcat"] = lc.stdout.strip()
            if dm.stdout.strip():
                sources["dmesg"] = dm.stdout.strip()
        else:
            os_info = self.detect_os()
            sudo = "" if str(self.spec.transport_config.get("user", "root")) == "root" else "sudo -n "
            collect_script = (
                f"echo __DAMF_SRC_DMESG__; ({sudo}dmesg 2>/dev/null || dmesg 2>/dev/null) | tail -n {int(max_lines)}; "
                f"echo __DAMF_SRC_SYSLOG__; ({sudo}tail -n {int(max_lines)} /var/log/syslog /var/log/messages 2>/dev/null || true); "
                f"echo __DAMF_SRC_JOURNAL__; ({sudo}journalctl -n {int(max_lines)} --no-pager 2>/dev/null || true); "
                f"echo __DAMF_SRC_AGENT__; (tail -n {int(max_lines)} /tmp/damf-agent.log 2>/dev/null || true)"
            )
            res = self.run(collect_script, timeout=20.0)
            current = ""
            buf: list[str] = []
            marker_map = {
                "__DAMF_SRC_DMESG__": "dmesg",
                "__DAMF_SRC_SYSLOG__": "syslog",
                "__DAMF_SRC_JOURNAL__": "journalctl",
                "__DAMF_SRC_AGENT__": "damf_agent",
            }
            for line in res.stdout.splitlines():
                stripped = line.strip()
                if stripped in marker_map:
                    if current and "\n".join(buf).strip():
                        sources[current] = "\n".join(buf).strip()
                    current = marker_map[stripped]
                    buf = []
                else:
                    buf.append(line)
            if current and "\n".join(buf).strip():
                sources[current] = "\n".join(buf).strip()
            sources.setdefault("os_summary", f"OS: {os_info.get('pretty_name', 'Unknown')}")

        # Build combined formatted log bundle text
        sections_text: list[str] = [
            f"# DAMF System Log Bundle — Device: {self.name} ({self.board_type})",
            f"# Collected At: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(now))}",
            "",
        ]
        for src_name, content in sources.items():
            sections_text.append(f"==================== [{src_name.upper()}] ====================")
            sections_text.append(content)
            sections_text.append("")
        combined_text = "\n".join(sections_text)

        saved_path_str = ""
        if output_dir is not None:
            out_dir = Path(output_dir)
            out_dir.mkdir(parents=True, exist_ok=True)
            bundle_file = out_dir / f"{self.name}_system_logs_{ts_str}.log"
            bundle_file.write_text(combined_text, encoding="utf-8")
            saved_path_str = str(bundle_file)
            copied_files.append(saved_path_str)

            for rfile in remote_files or []:
                local_target = out_dir / f"{self.name}_{Path(rfile).name}"
                if self.spec.transport_config.get("simulated", False):
                    local_target.write_text(f"# Simulated copy of {rfile} from {self.name}\n{combined_text}", encoding="utf-8")
                else:
                    self.download(rfile, local_target)
                copied_files.append(str(local_target))

        result = {
            "device": self.name,
            "collected_at": now,
            "sources": sources,
            "combined_text": combined_text,
            "saved_path": saved_path_str,
            "copied_files": copied_files,
        }
        self.spec.attributes["last_collected_logs"] = result
        return result

    def __repr__(self) -> str:
        return (
            f"<Device name={self.name!r} type={self.board_type!r} "
            f"ip={self.ip!r} transport={self.spec.transport!r} state={self.state!r}>"
        )
