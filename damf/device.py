"""High-level Device API combining metadata, transport, power control, and bootloader workflows."""

from __future__ import annotations

import logging
from pathlib import Path
import time
from typing import Any, Callable

from damf.exceptions import TransportError
from damf.models import CommandResult, DeviceSpec, TestCaseResult, TestSuiteResult
from damf.power import PowerController, create_power_controller
from damf.transports import SerialTransport, Transport, create_transport


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

    def reboot(self, delay_sec: float = 0.2) -> None:
        """Power cycle the device."""
        self.logger.info("Rebooting %s", self.name)
        self.power.reboot(delay_sec=delay_sec)

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

    def __repr__(self) -> str:
        return (
            f"<Device name={self.name!r} type={self.board_type!r} "
            f"ip={self.ip!r} transport={self.spec.transport!r} state={self.state!r}>"
        )
