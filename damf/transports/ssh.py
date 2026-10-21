"""SSH/SCP transport for embedded Linux boards (Raspberry Pi, BeagleBone, TI Linux, etc.)."""

from __future__ import annotations

from pathlib import Path
import shlex
import socket
import subprocess
import time

from damf.exceptions import CommandTimeoutError, TransportError
from damf.models import CommandResult, DeviceSpec
from damf.transports.base import Transport


class SSHTransport(Transport):
    """Communicates with Linux targets over OpenSSH / Dropbear SSH and SCP."""

    defproperty_defaults = {
        "user": "root",
        "port": 22,
        "strict_host_key_checking": False,
        "connect_timeout": 10,
    }

    @property
    def host(self) -> str:
        return self.spec.ip_address or self.config.get("host", "")

    @property
    def user(self) -> str:
        return str(self.config.get("user", "root"))

    @property
    def port(self) -> int:
        return int(self.config.get("port", 22))

    @property
    def identity_file(self) -> str | None:
        return self.config.get("identity_file") or self.config.get("key_filename")

    def _ssh_base_args(self, is_scp: bool = False) -> list[str]:
        binary = "scp" if is_scp else "ssh"
        port_flag = "-P" if is_scp else "-p"
        args = [
            binary,
            port_flag,
            str(self.port),
            "-o",
            "BatchMode=yes",
            "-o",
            f"ConnectTimeout={int(self.config.get('connect_timeout', 10))}",
        ]
        if not self.config.get("strict_host_key_checking", False):
            args.extend(["-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null"])
        if self.identity_file:
            args.extend(["-i", str(self.identity_file)])
        return args

    def connect(self) -> None:
        if not self.host:
            raise TransportError(f"Device '{self.spec.name}' has no IP address configured for SSH")
        if self.config.get("simulated", False):
            self.connected = True
            return
        try:
            with socket.create_connection((self.host, self.port), timeout=float(self.config.get("connect_timeout", 5))):
                self.connected = True
        except OSError as exc:
            raise TransportError(f"Cannot reach SSH port {self.host}:{self.port} for '{self.spec.name}': {exc}") from exc

    def disconnect(self) -> None:
        self.connected = False

    def run(
        self,
        command: str,
        timeout: float = 60.0,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
    ) -> CommandResult:
        if not self.host:
            raise TransportError(f"Device '{self.spec.name}' has no IP address for SSH execution")

        remote_cmd = command
        if cwd:
            remote_cmd = f"cd {shlex.quote(cwd)} && {remote_cmd}"
        if env:
            exports = " ".join(f"{k}={shlex.quote(str(v))}" for k, v in env.items())
            remote_cmd = f"export {exports}; {remote_cmd}"

        if self.config.get("simulated", False):
            return CommandResult(
                command=command,
                returncode=0,
                stdout=f"[simulated-ssh:{self.spec.name}] {command}\n",
                stderr="",
                duration_sec=0.01,
                device_name=self.spec.name,
            )

        ssh_cmd = self._ssh_base_args(is_scp=False) + [
            f"{self.user}@{self.host}",
            f"sh -c {shlex.quote(remote_cmd)}",
        ]
        start = time.monotonic()
        try:
            proc = subprocess.run(
                ssh_cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise CommandTimeoutError(
                f"SSH command timed out after {timeout}s on '{self.spec.name}': {command}"
            ) from exc
        except OSError as exc:
            raise TransportError(f"SSH execution failed on '{self.spec.name}': {exc}") from exc

        return CommandResult(
            command=command,
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            duration_sec=round(time.monotonic() - start, 4),
            device_name=self.spec.name,
        )

    def upload(self, local_path: str | Path, remote_path: str) -> None:
        if self.config.get("simulated", False):
            return
        src = Path(local_path)
        if not src.exists():
            raise TransportError(f"Local path does not exist for upload: {src}")
        scp_cmd = self._ssh_base_args(is_scp=True)
        if src.is_dir():
            scp_cmd.append("-r")
        scp_cmd.extend([str(src), f"{self.user}@{self.host}:{remote_path}"])
        proc = subprocess.run(scp_cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            raise TransportError(f"SCP upload to '{self.spec.name}' failed: {proc.stderr}")

    def download(self, remote_path: str, local_path: str | Path) -> None:
        if self.config.get("simulated", False):
            return
        dst = Path(local_path)
        dst.parent.mkdir(parents=True, exist_ok=True)
        scp_cmd = self._ssh_base_args(is_scp=True) + [
            "-r",
            f"{self.user}@{self.host}:{remote_path}",
            str(dst),
        ]
        proc = subprocess.run(scp_cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            raise TransportError(f"SCP download from '{self.spec.name}' failed: {proc.stderr}")
