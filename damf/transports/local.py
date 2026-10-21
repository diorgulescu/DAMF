"""Local shell and simulated transports for local testing, CI, and host-side commands."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import time

from damf.exceptions import CommandTimeoutError, TransportError
from damf.models import CommandResult, DeviceSpec
from damf.transports.base import Transport


class LocalTransport(Transport):
    """Executes commands and file transfers directly on the local machine."""

    def connect(self) -> None:
        self.connected = True

    def disconnect(self) -> None:
        self.connected = False

    def run(
        self,
        command: str,
        timeout: float = 60.0,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
    ) -> CommandResult:
        merged_env = os.environ.copy()
        if env:
            merged_env.update({k: str(v) for k, v in env.items()})
        start = time.monotonic()
        try:
            proc = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=merged_env,
                cwd=cwd,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise CommandTimeoutError(
                f"Local command timed out after {timeout}s on '{self.spec.name}': {command}"
            ) from exc
        return CommandResult(
            command=command,
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            duration_sec=round(time.monotonic() - start, 4),
            device_name=self.spec.name,
        )

    def upload(self, local_path: str | Path, remote_path: str) -> None:
        src = Path(local_path)
        dst = Path(remote_path)
        if not src.exists():
            raise TransportError(f"Local source path does not exist: {src}")
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dst)

    def download(self, remote_path: str, local_path: str | Path) -> None:
        self.upload(remote_path, local_path)
