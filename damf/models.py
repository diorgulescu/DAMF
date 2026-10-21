"""Core data models for DAMF devices, reservations, command results, and test jobs."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
import time
from typing import Any


class DeviceState(str, Enum):
    """Operational states of a device in the lab pool."""

    AVAILABLE = "available"
    RESERVED = "reserved"
    OFFLINE = "offline"
    MAINTENANCE = "maintenance"
    BOOTING = "booting"
    RUNNING_TESTS = "running_tests"


class TransportType(str, Enum):
    """Supported communication transports for lab devices."""

    SSH = "ssh"
    SERIAL = "serial"
    ADB = "adb"
    LOCAL = "local"


class PowerType(str, Enum):
    """Supported power controller backends."""

    SIMULATED = "simulated"
    WEBHOOK = "webhook"
    USB_HUB = "usb_hub"
    IPMI = "ipmi"
    COMMAND = "command"


@dataclass
class CommandResult:
    """Result of executing a command on a target device."""

    command: str
    returncode: int
    stdout: str = ""
    stderr: str = ""
    duration_sec: float = 0.0
    device_name: str = ""

    @property
    def ok(self) -> bool:
        """Return True if the command exited with code 0."""
        return self.returncode == 0

    def check(self) -> "CommandResult":
        """Raise RuntimeError if returncode is non-zero, otherwise return self."""
        if not self.ok:
            raise RuntimeError(
                f"Command '{self.command}' failed on '{self.device_name}' "
                f"(exit {self.returncode}): {self.stderr or self.stdout}"
            )
        return self


@dataclass
class DeviceSpec:
    """Metadata and connection profile describing a lab device or development board."""

    name: str
    board_type: str = "generic-linux"
    arch: str = "arm64"
    ip_address: str = ""
    mac_address: str = ""
    subnet: str = "192.168.1.0/24"
    transport: str = TransportType.SSH.value
    transport_config: dict[str, Any] = field(default_factory=dict)
    power_type: str = PowerType.SIMULATED.value
    power_config: dict[str, Any] = field(default_factory=dict)
    bootloader: str = "u-boot"
    cpu: str = ""
    eth_ports: int = 1
    deployed_image: str = ""
    state: str = DeviceState.AVAILABLE.value
    power_state: str = "off"
    owner: str = ""
    reservation_id: str = ""
    tags: list[str] = field(default_factory=list)
    attributes: dict[str, Any] = field(default_factory=dict)
    boot_commands: dict[str, list[str]] = field(default_factory=dict)
    connected_to: list[str] = field(default_factory=list)
    last_seen: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize DeviceSpec to a plain dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DeviceSpec":
        """Construct a DeviceSpec from a dictionary, ignoring unknown keys."""
        known_fields = set(cls.__dataclass_fields__.keys())
        filtered = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered)


@dataclass
class Reservation:
    """Represents an active lease on a device in the ResourcePool."""

    reservation_id: str
    device_name: str
    owner: str
    created_at: float
    expires_at: float
    purpose: str = ""

    @property
    def is_expired(self) -> bool:
        return time.time() > self.expires_at

    @property
    def remaining_seconds(self) -> float:
        return max(0.0, self.expires_at - time.time())

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["remaining_seconds"] = round(self.remaining_seconds, 1)
        data["is_expired"] = self.is_expired
        return data


@dataclass
class TestCaseResult:
    """Single test case execution outcome."""

    name: str
    status: str  # PASS, FAIL, SKIP
    duration_sec: float = 0.0
    stdout: str = ""
    message: str = ""


@dataclass
class TestSuiteResult:
    """Collection of test case outcomes for a device or test run."""

    suite_name: str
    device_name: str = ""
    cases: list[TestCaseResult] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)

    @property
    def passed(self) -> int:
        return sum(1 for c in self.cases if c.status.upper() == "PASS")

    @property
    def failed(self) -> int:
        return sum(1 for c in self.cases if c.status.upper() == "FAIL")

    @property
    def skipped(self) -> int:
        return sum(1 for c in self.cases if c.status.upper() == "SKIP")

    def to_dict(self) -> dict[str, Any]:
        return {
            "suite_name": self.suite_name,
            "device_name": self.device_name,
            "timestamp": self.timestamp,
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "total": len(self.cases),
            "cases": [asdict(c) for c in self.cases],
        }
