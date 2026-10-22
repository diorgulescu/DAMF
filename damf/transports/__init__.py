"""Transport factory and exports."""

from __future__ import annotations

from damf.exceptions import ConfigurationError
from damf.models import DeviceSpec, TransportType
from damf.transports.adb import ADBTransport
from damf.transports.base import Transport
from damf.transports.local import LocalTransport
from damf.transports.serial_transport import SerialTransport
from damf.transports.ssh import (
    SSHTransport,
    determine_reboot_command,
    parse_os_probe_output,
)


def create_transport(spec: DeviceSpec) -> Transport:
    """Instantiate the appropriate Transport implementation for a DeviceSpec."""
    kind = (spec.transport or TransportType.SSH.value).lower()
    if kind == TransportType.SSH.value:
        return SSHTransport(spec)
    if kind == TransportType.SERIAL.value:
        return SerialTransport(spec)
    if kind == TransportType.ADB.value:
        return ADBTransport(spec)
    if kind == TransportType.LOCAL.value:
        return LocalTransport(spec)
    raise ConfigurationError(f"Unsupported transport type '{spec.transport}' for device '{spec.name}'")


__all__ = [
    "Transport",
    "SSHTransport",
    "SerialTransport",
    "ADBTransport",
    "LocalTransport",
    "create_transport",
    "parse_os_probe_output",
    "determine_reboot_command",
]
