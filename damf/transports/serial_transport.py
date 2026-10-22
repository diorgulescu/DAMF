"""Serial / UART and U-Boot bootloader transport for embedded boards (TI, Raspberry Pi UART, etc.)."""

from __future__ import annotations

import os
from pathlib import Path
import select
import shutil
import time
from typing import Any

from damf.exceptions import TransportError
from damf.models import CommandResult, DeviceSpec
from damf.transports.base import Transport

try:
    import serial as _pyserial
except ImportError:
    _pyserial = None

try:
    import termios as _termios
    import tty as _tty
except ImportError:
    _termios = None  # type: ignore[assignment]
    _tty = None  # type: ignore[assignment]


def device_supports_serial(spec: DeviceSpec) -> bool:
    """Return True if `spec` is configured for or supports UART/Serial communication."""
    if (spec.transport or "").lower() == "serial":
        return True
    tc = spec.transport_config or {}
    if tc.get("serial_port"):
        return True
    port_val = str(tc.get("port", ""))
    if port_val.startswith(("/dev/", "COM", "tty")):
        return True
    if (spec.attributes or {}).get("serial_port"):
        return True
    if "serial" in (spec.tags or []) or "uart" in (spec.tags or []):
        return True
    return False


class _PosixSerialPort:
    """Zero-dependency POSIX `termios` serial port wrapper for Linux & macOS when `pyserial` is not installed."""

    def __init__(self, port: str, baudrate: int = 115200, timeout: float = 2.0):
        if _termios is None or _tty is None:
            raise TransportError("POSIX termios is not available on this platform; install pyserial")
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        self._configure_termios()

    def _configure_termios(self) -> None:
        baud_const = getattr(_termios, f"B{self.baudrate}", getattr(_termios, "B115200", None))
        attrs = _termios.tcgetattr(self.fd)
        # 8N1 raw mode, no hardware flow control
        attrs[0] = 0  # iflag
        attrs[1] = 0  # oflag
        attrs[2] = _termios.CS8 | _termios.CREAD | _termios.CLOCAL  # cflag
        attrs[3] = 0  # lflag
        if baud_const is not None:
            attrs[4] = baud_const  # ispeed
            attrs[5] = baud_const  # ospeed
        _termios.tcsetattr(self.fd, _termios.TCSANOW, attrs)
        _termios.tcflush(self.fd, _termios.TCIOFLUSH)

    def write(self, data: bytes) -> int:
        return os.write(self.fd, data)

    def flush(self) -> None:
        if _termios is not None:
            _termios.tcdrain(self.fd)

    def readline(self) -> bytes:
        deadline = time.monotonic() + self.timeout
        buf = bytearray()
        while time.monotonic() < deadline:
            remaining = max(0.01, deadline - time.monotonic())
            rlist, _, _ = select.select([self.fd], [], [], remaining)
            if not rlist:
                break
            try:
                chunk = os.read(self.fd, 1)
            except BlockingIOError:
                continue
            if not chunk:
                break
            buf.extend(chunk)
            if chunk == b"\n":
                break
        return bytes(buf)

    def close(self) -> None:
        if self.fd >= 0:
            try:
                os.close(self.fd)
            except OSError:
                pass
            self.fd = -1


class SerialTransport(Transport):
    """Communicates over UART/Serial port or console command, including U-Boot and OS login automation."""

    def __init__(self, spec: DeviceSpec):
        super().__init__(spec)
        self._serial_conn: Any = None
        self.command_history: list[str] = []

    @property
    def supports_serial(self) -> bool:
        return device_supports_serial(self.spec)

    @property
    def port(self) -> str:
        if self.config.get("serial_port"):
            return str(self.config["serial_port"])
        port_cfg = self.config.get("port")
        if isinstance(port_cfg, str) and (port_cfg.startswith(("/dev/", "COM", "tty")) or not port_cfg.isdigit()):
            return port_cfg
        if self.spec.attributes.get("serial_port"):
            return str(self.spec.attributes["serial_port"])
        return "/dev/ttyUSB0"

    @property
    def baudrate(self) -> int:
        return int(self.config.get("baudrate") or self.spec.attributes.get("baudrate") or 115200)

    @property
    def uboot_prompt(self) -> str:
        return str(self.config.get("uboot_prompt", "U-Boot>"))

    @property
    def login_prompt(self) -> str:
        return str(self.config.get("login_prompt", "login:"))

    @property
    def shell_prompt(self) -> str:
        return str(self.config.get("shell_prompt", "#"))

    @property
    def user(self) -> str:
        return str(self.config.get("user", "root"))

    def build_interactive_serial_command(self) -> list[str]:
        """Return the CLI argv list to open an interactive serial terminal to this device."""
        if not self.supports_serial:
            raise TransportError(f"Device '{self.spec.name}' does not have a serial port configured")
        if shutil.which("picocom"):
            return ["picocom", "-b", str(self.baudrate), self.port]
        if shutil.which("tio"):
            return ["tio", "-b", str(self.baudrate), self.port]
        if shutil.which("minicom"):
            return ["minicom", "-b", str(self.baudrate), "-D", self.port]
        if shutil.which("screen"):
            return ["screen", self.port, str(self.baudrate)]
        return ["python3", "-m", "serial.tools.miniterm", self.port, str(self.baudrate)]

    def connect(self) -> None:
        if not self.supports_serial:
            raise TransportError(
                f"Device '{self.spec.name}' does not support serial connections "
                "(configure serial_port in transport_config or attributes)"
            )
        if self.config.get("simulated", False):
            self.connected = True
            self.spec.attributes["serial_port"] = self.port
            self.spec.attributes["baudrate"] = self.baudrate
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
            try:
                self._serial_conn = _PosixSerialPort(
                    port=self.port,
                    baudrate=self.baudrate,
                    timeout=float(self.config.get("timeout", 2.0)),
                )
                self.connected = True
                return
            except Exception as exc:
                raise TransportError(f"Failed to open POSIX serial port {self.port}: {exc}") from exc
        raise TransportError(
            f"Serial port '{self.port}' for device '{self.spec.name}' is not available "
            "(set transport_config.simulated=True for dry-run testing)"
        )

    def detect_console_state(self, auto_login: bool = True) -> dict[str, Any]:
        """Probe the serial console to determine if it is at U-Boot, OS login, or a shell prompt."""
        if not self.connected:
            self.connect()

        if self.config.get("simulated", False):
            sim_state = str(
                self.config.get("console_state")
                or self.config.get("simulated_console_state")
                or "shell"
            )
            prompt = self.uboot_prompt if sim_state == "uboot" else f"{self.user}@{self.spec.name}:~#"
            info = {
                "device": self.spec.name,
                "connected": True,
                "port": self.port,
                "serial_port": self.port,
                "baudrate": self.baudrate,
                "databits": int(self.config.get("databits", 8)),
                "parity": str(self.config.get("parity", "N")),
                "stopbits": int(self.config.get("stopbits", 1)),
                "console_state": sim_state,
                "prompt": prompt,
                "interactive_cmd": " ".join(self.build_interactive_serial_command()),
            }
            self.spec.attributes["serial_state"] = info
            return info

        assert self._serial_conn is not None
        self._serial_conn.write(b"\r\n")
        self._serial_conn.flush()
        collected: list[str] = []
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            raw = self._serial_conn.readline()
            if not raw:
                break
            collected.append(raw.decode("utf-8", errors="replace"))
        banner = "".join(collected).strip()

        if self.uboot_prompt in banner or "=>" in banner:
            state = "uboot"
        elif self.login_prompt.lower() in banner.lower():
            state = "login"
            if auto_login:
                self._serial_conn.write(f"{self.user}\r\n".encode("utf-8"))
                self._serial_conn.flush()
                state = "shell"
        else:
            state = "shell"

        info = {
            "device": self.spec.name,
            "connected": True,
            "port": self.port,
            "serial_port": self.port,
            "baudrate": self.baudrate,
            "databits": int(self.config.get("databits", 8)),
            "parity": str(self.config.get("parity", "N")),
            "stopbits": int(self.config.get("stopbits", 1)),
            "console_state": state,
            "prompt": banner.splitlines()[-1] if banner else self.shell_prompt,
            "interactive_cmd": " ".join(self.build_interactive_serial_command()),
        }
        self.spec.attributes["serial_state"] = info
        return info

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
        if not self.supports_serial:
            raise TransportError(f"Device '{self.spec.name}' does not support serial execution")

        start = time.monotonic()
        full_cmd = command
        if cwd:
            full_cmd = f"cd {cwd} && {full_cmd}"
        if env:
            exports = " ".join(f"{k}={v}" for k, v in env.items())
            full_cmd = f"export {exports}; {full_cmd}"

        self.command_history.append(full_cmd)

        if self.config.get("simulated", False):
            sim_state = str(
                self.config.get("console_state")
                or self.config.get("simulated_console_state")
                or "shell"
            )
            if sim_state == "uboot":
                sim_out = f"[simulated-uboot:{self.port}@{self.baudrate}] U-Boot 2024.04 ({self.spec.board_type}) => {full_cmd}\n"
            elif "uname" in full_cmd:
                sim_out = f"[simulated-serial:{self.port}@{self.baudrate}] Linux {self.spec.name} 6.6.20 {self.spec.arch} GNU/Linux\n"
            else:
                sim_out = f"[simulated-serial:{self.port}@{self.baudrate}] {full_cmd}\n"
            return CommandResult(
                command=command,
                returncode=0,
                stdout=sim_out,
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
