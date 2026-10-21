"""Android Debug Bridge (ADB) transport for Android phones, tablets, and SBCs."""

from __future__ import annotations

from pathlib import Path
import shlex
import subprocess
import time

from damf.exceptions import CommandTimeoutError, TransportError
from damf.models import CommandResult, DeviceSpec
from damf.transports.base import Transport


class ADBTransport(Transport):
    """Communicates with Android devices over USB or TCP/IP using the `adb` CLI."""

    @property
    def serial(self) -> str:
        """Return the ADB device serial or IP:port identifier."""
        return (
            str(self.config.get("serial", ""))
            or (f"{self.spec.ip_address}:5555" if self.spec.ip_address else "")
            or self.spec.name
        )

    def _adb_base(self) -> list[str]:
        adb_bin = str(self.config.get("adb_binary", "adb"))
        if self.serial:
            return [adb_bin, "-s", self.serial]
        return [adb_bin]

    def connect(self) -> None:
        if self.config.get("simulated", False):
            self.connected = True
            return
        if self.spec.ip_address and ":" in self.serial:
            proc = subprocess.run(
                [str(self.config.get("adb_binary", "adb")), "connect", self.serial],
                capture_output=True,
                text=True,
                check=False,
            )
            if proc.returncode != 0:
                raise TransportError(f"ADB connect to {self.serial} failed: {proc.stderr or proc.stdout}")
        res = self.run("getprop ro.build.version.release", timeout=10.0)
        if not res.ok:
            raise TransportError(f"ADB device '{self.serial}' is not responding: {res.stderr}")
        self.connected = True

    def disconnect(self) -> None:
        if not self.config.get("simulated", False) and self.spec.ip_address and ":" in self.serial:
            subprocess.run(
                [str(self.config.get("adb_binary", "adb")), "disconnect", self.serial],
                capture_output=True,
                text=True,
                check=False,
            )
        self.connected = False

    def run(
        self,
        command: str,
        timeout: float = 60.0,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
    ) -> CommandResult:
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
                stdout=f"[simulated-adb:{self.serial}] {remote_cmd}\n",
                stderr="",
                duration_sec=0.01,
                device_name=self.spec.name,
            )

        adb_cmd = self._adb_base() + ["shell", remote_cmd]
        start = time.monotonic()
        try:
            proc = subprocess.run(
                adb_cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise CommandTimeoutError(
                f"ADB command timed out after {timeout}s on '{self.spec.name}': {command}"
            ) from exc
        except OSError as exc:
            raise TransportError(f"ADB binary execution failed for '{self.spec.name}': {exc}") from exc

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
            raise TransportError(f"Local path does not exist for ADB push: {src}")
        proc = subprocess.run(
            self._adb_base() + ["push", str(src), remote_path],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            raise TransportError(f"ADB push failed on '{self.spec.name}': {proc.stderr}")

    def download(self, remote_path: str, local_path: str | Path) -> None:
        if self.config.get("simulated", False):
            return
        dst = Path(local_path)
        dst.parent.mkdir(parents=True, exist_ok=True)
        proc = subprocess.run(
            self._adb_base() + ["pull", remote_path, str(dst)],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            raise TransportError(f"ADB pull failed on '{self.spec.name}': {proc.stderr}")

    def install_apk(self, apk_path: str | Path, reinstall: bool = True) -> CommandResult:
        """Install an Android APK onto the target device."""
        if self.config.get("simulated", False):
            return CommandResult(
                command=f"adb install {apk_path}",
                returncode=0,
                stdout="Success\n",
                device_name=self.spec.name,
            )
        args = self._adb_base() + ["install"]
        if reinstall:
            args.append("-r")
        args.append(str(apk_path))
        proc = subprocess.run(args, capture_output=True, text=True, check=False)
        return CommandResult(
            command=" ".join(args),
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            device_name=self.spec.name,
        )

    def get_prop(self, prop_name: str) -> str:
        """Query an Android system property via `getprop`."""
        res = self.run(f"getprop {shlex.quote(prop_name)}", timeout=10.0)
        return res.stdout.strip()
