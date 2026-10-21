"""Serial / UART and U-Boot bootloader transport for embedded boards (TI, Raspberry Pi UART, etc.)."""

from __future__ import annotations

from pathlib import Path
import time
from typing import Any

from damf.exceptions import TransportError
from damf.models import CommandResult, DeviceSpec
from damf.transports.base import Transport

try:
    import serial as _pyserial
except ImportError:
    _pyserial = None


class SerialTransport(Transport):
    """Communicates over UART/Serial port or console command, including U-Boot automation."""

    def __init__(self, spec: DeviceSpec):
        super().__init__(spec)
        self._serial_conn: Any = None
        self.command_history: list[str] = []

    @property
    def port(self) -> str:
        return str(self.config.get("port", "/dev/ttyUSB0"))

    @property
    def baudrate(self) -> int:
        return int(self.config.get("baudrate", 115200))

    @property
    def uboot_prompt(self) -> str:
        return str(self.config.get("uboot_prompt", "U-Boot>"))

    @property
    def login_prompt(self) -> str:
        return str(self.config.get("login_prompt", "login:"))

    @property
    def shell_prompt(self) -> str:
        return str(self.config.get("shell_prompt", "#"))

    def connect(self) -> None:
        if self.config.get("simulated", False):
            self.connected = True
            return
        if _pyserial is not None and Path(self.port).exists():
            try:
                self._serial_conn = _pyserial.Serial(
                    port=self.port,
                    baudrate=self.baudrate,
                    timeout=float(self.config.get("timeout", 2.0)),
                )
                self.connected = True
                return
            except Exception as exc:
                raise TransportError(f"Failed to open serial port {self.port}: {exc}") from exc
        if Path(self.port).exists():
            self.connected = True
            return
        raise TransportError(
            f"Serial port '{self.port}' for device '{self.spec.name}' is not available "
            "(set transport_config.simulated=True for dry-run testing)"
        )

    def disconnect(self) -> None:
        if self._serial_conn is not None:
            try:
                self._serial_conn.close()
            except Exception:
                pass
            self._serial_conn = None
        self.connected = False

    def send_uboot_commands(
        self,
        commands: list[str],
        template_vars: dict[str, str] | None = None,
    ) -> list[str]:
        """Render placeholders ({IMAGE}, {DTB}, {ROOT_FS}) and send commands to U-Boot."""
        rendered: list[str] = []
        replacements = template_vars or {}
        for cmd in commands:
            line = cmd
            for key, val in replacements.items():
                placeholder = f"{{{key.upper()}}}"
                line = line.replace(placeholder, str(val))
            rendered.append(line)
            self.command_history.append(line)
            if self._serial_conn is not None:
                self._serial_conn.write((line + "\n").encode("utf-8"))
                self._serial_conn.flush()
        return rendered

    def run(
        self,
        command: str,
        timeout: float = 60.0,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
    ) -> CommandResult:
        start = time.monotonic()
        full_cmd = command
        if cwd:
            full_cmd = f"cd {cwd} && {full_cmd}"
        if env:
            exports = " ".join(f"{k}={v}" for k, v in env.items())
            full_cmd = f"export {exports}; {full_cmd}"

        self.command_history.append(full_cmd)

        if self.config.get("simulated", False):
            return CommandResult(
                command=command,
                returncode=0,
                stdout=f"[simulated-serial:{self.port}] {full_cmd}\n",
                stderr="",
                duration_sec=round(time.monotonic() - start, 4),
                device_name=self.spec.name,
            )

        if self._serial_conn is None:
            self.connect()

        if self._serial_conn is not None:
            marker = f"__DAMF_RC_{int(time.time() * 1000)}__"
            payload = f"{full_cmd}; echo {marker}:$?\n"
            self._serial_conn.write(payload.encode("utf-8"))
            self._serial_conn.flush()

            deadline = time.monotonic() + timeout
            output_lines: list[str] = []
            returncode = 0
            while time.monotonic() < deadline:
                raw = self._serial_conn.readline()
                if not raw:
                    continue
                line = raw.decode("utf-8", errors="replace")
                if marker in line:
                    _, _, rc_text = line.partition(f"{marker}:")
                    try:
                        returncode = int(rc_text.strip().split()[0])
                    except (ValueError, IndexError):
                        returncode = 0
                    break
                output_lines.append(line)
            return CommandResult(
                command=command,
                returncode=returncode,
                stdout="".join(output_lines),
                stderr="",
                duration_sec=round(time.monotonic() - start, 4),
                device_name=self.spec.name,
            )

        raise TransportError(f"Serial connection not active on '{self.spec.name}'")

    def upload(self, local_path: str | Path, remote_path: str) -> None:
        src = Path(local_path)
        if not src.exists():
            raise TransportError(f"Local file not found for serial upload: {src}")
        if self.config.get("simulated", False):
            self.command_history.append(f"upload:{src}->{remote_path}")
            return
        import base64

        encoded = base64.b64encode(src.read_bytes()).decode("ascii")
        self.run(f"echo '{encoded}' | base64 -d > {remote_path}").check()

    def download(self, remote_path: str, local_path: str | Path) -> None:
        dst = Path(local_path)
        dst.parent.mkdir(parents=True, exist_ok=True)
        if self.config.get("simulated", False):
            self.command_history.append(f"download:{remote_path}->{dst}")
            return
        import base64

        res = self.run(f"base64 {remote_path}").check()
        dst.write_bytes(base64.b64decode(res.stdout.strip()))
