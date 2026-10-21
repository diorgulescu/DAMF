"""Network, USB/Serial, and ADB device discovery scanners for DAMF."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import glob
import ipaddress
import re
import socket
import subprocess
from typing import Any

from damf.discovery.oui import lookup_mac_vendor, normalize_mac
from damf.models import DeviceSpec, DeviceState, TransportType


class ARPScanner:
    """Discovers networked boards from the system ARP table and matches embedded MAC OUIs."""

    ARP_LINE_RE = re.compile(
        r"(?P<host>\S+)\s+\((?P<ip>\d+\.\d+\.\d+\.\d+)\)\s+at\s+(?P<mac>[0-9a-fA-F:]{11,17})"
    )

    def scan(self, arp_output: str | None = None, only_known_vendors: bool = False) -> list[DeviceSpec]:
        if arp_output is None:
            try:
                proc = subprocess.run(["arp", "-a"], capture_output=True, text=True, timeout=5.0, check=False)
                arp_output = proc.stdout
            except OSError:
                arp_output = ""

        discovered: list[DeviceSpec] = []
        for line in arp_output.splitlines():
            match = self.ARP_LINE_RE.search(line)
            if not match:
                continue
            host = match.group("host")
            ip = match.group("ip")
            raw_mac = match.group("mac")
            if raw_mac.lower() in ("(incomplete)", "ff:ff:ff:ff:ff:ff"):
                continue
            mac = normalize_mac(raw_mac)
            vendor_info = lookup_mac_vendor(mac)
            if only_known_vendors and vendor_info is None:
                continue

            if vendor_info is not None:
                vendor, board_type, arch = vendor_info
                tags = ["discovered", "arp", vendor.lower().replace(" ", "-")]
            else:
                vendor = "Unknown"
                board_type = "generic-linux"
                arch = "arm64"
                tags = ["discovered", "arp"]

            suffix = mac.replace(":", "")[-4:].lower()
            name = host if host and host != "?" else f"{board_type}-{suffix}"
            subnet = ".".join(ip.split(".")[:3]) + ".0/24"
            discovered.append(
                DeviceSpec(
                    name=name,
                    board_type=board_type,
                    arch=arch,
                    ip_address=ip,
                    mac_address=mac,
                    subnet=subnet,
                    transport=TransportType.SSH.value,
                    state=DeviceState.AVAILABLE.value,
                    power_state="on",
                    tags=tags,
                    attributes={"vendor": vendor, "discovery_source": "arp"},
                )
            )
        return discovered


class MDNSScanner:
    """Discovers devices advertising mDNS / Zeroconf (.local) hostnames on the local network."""

    DEFAULT_HOSTNAMES = (
        ("raspberrypi.local", "raspberry-pi-4", "arm64"),
        ("raspberrypi4.local", "raspberry-pi-4", "arm64"),
        ("raspberrypi5.local", "raspberry-pi-5", "arm64"),
        ("beaglebone.local", "beaglebone-black", "arm"),
        ("am62x-evm.local", "ti-am62x", "arm64"),
        ("am335x-evm.local", "ti-am335x", "arm"),
        ("jetson.local", "jetson-nano", "arm64"),
    )

    def scan(
        self,
        candidate_hosts: list[tuple[str, str, str]] | None = None,
        resolver: Any = None,
    ) -> list[DeviceSpec]:
        hosts = candidate_hosts if candidate_hosts is not None else list(self.DEFAULT_HOSTNAMES)
        resolve_fn = resolver or socket.gethostbyname
        found: list[DeviceSpec] = []
        for hostname, board_type, arch in hosts:
            try:
                ip = resolve_fn(hostname)
            except OSError:
                continue
            if not ip or ip.startswith("127."):
                continue
            subnet = ".".join(ip.split(".")[:3]) + ".0/24"
            clean_name = hostname.removesuffix(".local")
            found.append(
                DeviceSpec(
                    name=clean_name,
                    board_type=board_type,
                    arch=arch,
                    ip_address=ip,
                    subnet=subnet,
                    transport=TransportType.SSH.value,
                    state=DeviceState.AVAILABLE.value,
                    power_state="on",
                    tags=["discovered", "mdns"],
                    attributes={"hostname": hostname, "discovery_source": "mdns"},
                )
            )
        return found


class SubnetScanner:
    """Probes IP addresses in a subnet for open SSH (22) or ADB-over-TCP (5555) ports."""

    def __init__(self, timeout: float = 0.35, max_workers: int = 32):
        self.timeout = timeout
        self.max_workers = max_workers

    def _probe_host(self, ip: str) -> DeviceSpec | None:
        subnet = ".".join(ip.split(".")[:3]) + ".0/24"
        # Check SSH port 22
        try:
            with socket.create_connection((ip, 22), timeout=self.timeout) as sock:
                sock.settimeout(self.timeout)
                try:
                    banner = sock.recv(128).decode("utf-8", errors="ignore").strip()
                except OSError:
                    banner = "SSH"
                board_type = "raspberry-pi" if "raspbian" in banner.lower() or "debian" in banner.lower() else "linux-board"
                return DeviceSpec(
                    name=f"{board_type}-{ip.split('.')[-1]}",
                    board_type=board_type,
                    arch="arm64",
                    ip_address=ip,
                    subnet=subnet,
                    transport=TransportType.SSH.value,
                    state=DeviceState.AVAILABLE.value,
                    power_state="on",
                    tags=["discovered", "subnet-scan", "ssh"],
                    attributes={"ssh_banner": banner, "discovery_source": "subnet"},
                )
        except OSError:
            pass

        # Check wireless ADB port 5555
        try:
            with socket.create_connection((ip, 5555), timeout=self.timeout):
                return DeviceSpec(
                    name=f"android-{ip.split('.')[-1]}",
                    board_type="android-device",
                    arch="arm64",
                    ip_address=ip,
                    subnet=subnet,
                    transport=TransportType.ADB.value,
                    transport_config={"serial": f"{ip}:5555"},
                    state=DeviceState.AVAILABLE.value,
                    power_state="on",
                    tags=["discovered", "subnet-scan", "adb"],
                    attributes={"discovery_source": "subnet"},
                )
        except OSError:
            return None

    def scan(self, cidr_or_ips: str | list[str]) -> list[DeviceSpec]:
        if isinstance(cidr_or_ips, str):
            net = ipaddress.ip_network(cidr_or_ips, strict=False)
            targets = [str(ip) for ip in net.hosts()]
        else:
            targets = list(cidr_or_ips)

        results: list[DeviceSpec] = []
        with ThreadPoolExecutor(max_workers=min(self.max_workers, max(1, len(targets)))) as pool:
            futures = {pool.submit(self._probe_host, ip): ip for ip in targets}
            for fut in as_completed(futures):
                spec = fut.result()
                if spec is not None:
                    results.append(spec)
        return results


class SerialScanner:
    """Discovers locally connected USB-to-UART serial boards (/dev/ttyUSB*, /dev/ttyACM*, /dev/cu.usb*)."""

    PATTERNS = (
        "/dev/ttyUSB*",
        "/dev/ttyACM*",
        "/dev/cu.usbserial*",
        "/dev/cu.usbmodem*",
    )

    def scan(self, custom_ports: list[str] | None = None) -> list[DeviceSpec]:
        ports: list[str] = []
        if custom_ports is not None:
            ports = list(custom_ports)
        else:
            for pattern in self.PATTERNS:
                ports.extend(sorted(glob.glob(pattern)))

        devices: list[DeviceSpec] = []
        for port in ports:
            short = port.split("/")[-1].replace(".", "-")
            devices.append(
                DeviceSpec(
                    name=f"serial-{short}",
                    board_type="serial-board",
                    arch="arm",
                    transport=TransportType.SERIAL.value,
                    transport_config={"port": port, "baudrate": 115200},
                    state=DeviceState.AVAILABLE.value,
                    power_state="on",
                    tags=["discovered", "serial", "uart"],
                    attributes={"serial_port": port, "discovery_source": "serial"},
                )
            )
        return devices


class ADBScanner:
    """Discovers USB and network-attached Android phones/devices via `adb devices -l`."""

    def scan(self, adb_output: str | None = None) -> list[DeviceSpec]:
        if adb_output is None:
            try:
                proc = subprocess.run(
                    ["adb", "devices", "-l"],
                    capture_output=True,
                    text=True,
                    timeout=5.0,
                    check=False,
                )
                adb_output = proc.stdout if proc.returncode == 0 else ""
            except OSError:
                adb_output = ""

        devices: list[DeviceSpec] = []
        for raw_line in adb_output.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("List of devices") or line.startswith("*"):
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            serial_id, status = parts[0], parts[1]
            if status not in ("device", "online", "unauthorized", "offline"):
                continue
            kv: dict[str, str] = {}
            for token in parts[2:]:
                if ":" in token:
                    k, _, v = token.partition(":")
                    kv[k] = v
            model = kv.get("model", "android").lower().replace("_", "-")
            ip_addr = serial_id.split(":")[0] if ":" in serial_id else ""
            state = DeviceState.AVAILABLE.value if status in ("device", "online") else DeviceState.OFFLINE.value
            clean_serial = serial_id.replace(":", "-").replace(".", "-")
            devices.append(
                DeviceSpec(
                    name=f"{model}-{clean_serial}",
                    board_type="android",
                    arch="arm64",
                    ip_address=ip_addr,
                    transport=TransportType.ADB.value,
                    transport_config={"serial": serial_id},
                    state=state,
                    power_state="on" if state == DeviceState.AVAILABLE.value else "off",
                    tags=["discovered", "android", "adb"],
                    attributes={**kv, "adb_serial": serial_id, "discovery_source": "adb"},
                )
            )
        return devices


class DiscoveryEngine:
    """Orchestrates ARP, mDNS, Subnet, Serial, and ADB scanners and deduplicates results."""

    def __init__(self) -> None:
        self.arp = ARPScanner()
        self.mdns = MDNSScanner()
        self.subnet = SubnetScanner()
        self.serial = SerialScanner()
        self.adb = ADBScanner()

    def discover_all(
        self,
        include_arp: bool = True,
        include_mdns: bool = False,
        include_serial: bool = True,
        include_adb: bool = True,
        subnet_cidr: str | list[str] | None = None,
        only_known_arp_vendors: bool = False,
    ) -> list[DeviceSpec]:
        """Run enabled discovery scanners and return a deduplicated list of DeviceSpecs."""
        combined: list[DeviceSpec] = []
        if include_arp:
            combined.extend(self.arp.scan(only_known_vendors=only_known_arp_vendors))
        if include_mdns:
            combined.extend(self.mdns.scan())
        if subnet_cidr:
            combined.extend(self.subnet.scan(subnet_cidr))
        if include_serial:
            combined.extend(self.serial.scan())
        if include_adb:
            combined.extend(self.adb.scan())

        return self.deduplicate(combined)

    @staticmethod
    def deduplicate(specs: list[DeviceSpec]) -> list[DeviceSpec]:
        """Merge discovered specs that share an IP address, MAC address, or name."""
        by_key: dict[str, DeviceSpec] = {}
        seen_ips: dict[str, str] = {}
        seen_macs: dict[str, str] = {}

        for spec in specs:
            existing_name = None
            if spec.mac_address and spec.mac_address in seen_macs:
                existing_name = seen_macs[spec.mac_address]
            elif spec.ip_address and spec.ip_address in seen_ips:
                existing_name = seen_ips[spec.ip_address]
            elif spec.name in by_key:
                existing_name = spec.name

            if existing_name is not None:
                current = by_key[existing_name]
                if not current.mac_address and spec.mac_address:
                    current.mac_address = spec.mac_address
                if not current.ip_address and spec.ip_address:
                    current.ip_address = spec.ip_address
                if current.board_type in ("generic-linux", "linux-board") and spec.board_type not in (
                    "generic-linux",
                    "linux-board",
                ):
                    current.board_type = spec.board_type
                current.tags = sorted(set(current.tags) | set(spec.tags))
                current.attributes.update(spec.attributes)
            else:
                by_key[spec.name] = spec
                if spec.ip_address:
                    seen_ips[spec.ip_address] = spec.name
                if spec.mac_address:
                    seen_macs[spec.mac_address] = spec.name

        return list(by_key.values())
