"""DAMF — Device Automation and Management Framework.

Public Python SDK for discovering, reserving, controlling, and testing embedded
devices and development boards (Raspberry Pi, Texas Instruments, Linux SBCs, Android).
"""

from damf.agent import DAMFAgent, collect_telemetry, generate_posix_shell_agent
from damf.config import dump_yaml, load_config_file, safe_load_all_yaml, safe_load_yaml
from damf.device import Device
from damf.discovery import (
    ADBScanner,
    ARPScanner,
    DiscoveryEngine,
    MDNSScanner,
    SerialScanner,
    SubnetScanner,
    lookup_mac_vendor,
    normalize_mac,
)
from damf.exceptions import (
    CommandTimeoutError,
    ConfigurationError,
    DAMFError,
    DeviceBusyError,
    DeviceNotFoundError,
    ImageLoadFailed,
    PowerControlError,
    ReservationError,
    TransportError,
)
from damf.lab import Lab, RemoteLabClient
from damf.models import (
    CommandResult,
    DeviceSpec,
    DeviceState,
    PowerType,
    Reservation,
    TestCaseResult,
    TestSuiteResult,
    TransportType,
)
from damf.pool import ResourcePool
from damf.power import (
    CommandPowerController,
    IPMIPowerController,
    PowerController,
    SimulatedPowerController,
    SSHPowerController,
    USBHubPowerController,
    WebhookPowerController,
    create_power_controller,
)
from damf.results import ResultParser
from damf.transports import (
    ADBTransport,
    LocalTransport,
    SerialTransport,
    SSHTransport,
    Transport,
    create_transport,
    determine_reboot_command,
    device_supports_serial,
    parse_os_probe_output,
)
from damf.web import DAMFWebApp, create_http_server

__version__ = "2.0.0"

__all__ = [
    "__version__",
    "Lab",
    "RemoteLabClient",
    "Device",
    "DAMFAgent",
    "collect_telemetry",
    "generate_posix_shell_agent",
    "ResourcePool",
    "ResultParser",
    "DiscoveryEngine",
    "ARPScanner",
    "MDNSScanner",
    "SubnetScanner",
    "SerialScanner",
    "ADBScanner",
    "lookup_mac_vendor",
    "normalize_mac",
    "DeviceSpec",
    "DeviceState",
    "TransportType",
    "PowerType",
    "CommandResult",
    "Reservation",
    "TestCaseResult",
    "TestSuiteResult",
    "Transport",
    "SSHTransport",
    "SerialTransport",
    "ADBTransport",
    "LocalTransport",
    "create_transport",
    "device_supports_serial",
    "parse_os_probe_output",
    "determine_reboot_command",
    "PowerController",
    "SimulatedPowerController",
    "SSHPowerController",
    "WebhookPowerController",
    "USBHubPowerController",
    "IPMIPowerController",
    "CommandPowerController",
    "create_power_controller",
    "DAMFWebApp",
    "create_http_server",
    "load_config_file",
    "safe_load_yaml",
    "safe_load_all_yaml",
    "dump_yaml",
    "DAMFError",
    "ConfigurationError",
    "DeviceNotFoundError",
    "ReservationError",
    "DeviceBusyError",
    "TransportError",
    "CommandTimeoutError",
    "PowerControlError",
    "ImageLoadFailed",
]
