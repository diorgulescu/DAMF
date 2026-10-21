"""Base transport interface for communicating with lab devices."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from damf.models import CommandResult, DeviceSpec


class Transport(ABC):
    """Abstract base class for device communication transports (SSH, Serial, ADB, Local)."""

    def __init__(self, spec: DeviceSpec):
        self.spec = spec
        self.connected = False

    @property
    def config(self) -> dict[str, Any]:
        return self.spec.transport_config

    @abstractmethod
    def connect(self) -> None:
        """Establish a connection to the target device."""

    @abstractmethod
    def disconnect(self) -> None:
        """Close the active connection to the target device."""

    @abstractmethod
    def run(
        self,
        command: str,
        timeout: float = 60.0,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
    ) -> CommandResult:
        """Execute a command on the target device and return a CommandResult."""

    @abstractmethod
    def upload(self, local_path: str | Path, remote_path: str) -> None:
        """Copy a local file or directory to the target device."""

    @abstractmethod
    def download(self, remote_path: str, local_path: str | Path) -> None:
        """Copy a file or directory from the target device to the local host."""

    def is_alive(self) -> bool:
        """Check whether the device is reachable over this transport."""
        try:
            res = self.run("echo damf_ping", timeout=5.0)
            return res.ok and "damf_ping" in res.stdout
        except Exception:
            return False
