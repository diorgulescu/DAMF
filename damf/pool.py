"""SQLite-backed ResourcePool for managing device inventory, reservations, and test jobs."""

from __future__ import annotations

import json
import logging
from pathlib import Path
import sqlite3
import threading
import time
import uuid
from typing import Any

from damf.config import safe_load_all_yaml
from damf.exceptions import DeviceBusyError, DeviceNotFoundError, ReservationError
from damf.models import DeviceSpec, DeviceState, Reservation


class ResourcePool:
    """Thread-safe, SQLite-backed device inventory and reservation pool."""

    def __init__(
        self,
        db_path: str | Path = ":memory:",
        board_files_path: str | Path | None = None,
        logger_handle: logging.Logger | None = None,
    ):
        self.db_path = str(db_path)
        self.board_file_path = str(board_files_path) if board_files_path else ""
        self.logger = logger_handle or logging.getLogger("damf.pool")
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()
        if self.board_file_path and Path(self.board_file_path).exists():
            self.load_board_files(self.board_file_path)

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        with self._lock:
            try:
                self._conn.close()
            except Exception:
                pass

    def _init_schema(self) -> None:
        with self._lock, self._conn:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS devices (
                    name TEXT PRIMARY KEY,
                    board_type TEXT NOT NULL,
                    arch TEXT NOT NULL,
                    ip_address TEXT DEFAULT '',
                    mac_address TEXT DEFAULT '',
                    subnet TEXT DEFAULT '192.168.1.0/24',
                    transport TEXT DEFAULT 'ssh',
                    transport_config TEXT DEFAULT '{}',
                    power_type TEXT DEFAULT 'simulated',
                    power_config TEXT DEFAULT '{}',
                    bootloader TEXT DEFAULT 'u-boot',
                    cpu TEXT DEFAULT '',
                    eth_ports INTEGER DEFAULT 1,
                    deployed_image TEXT DEFAULT '',
                    state TEXT DEFAULT 'available',
                    power_state TEXT DEFAULT 'off',
                    owner TEXT DEFAULT '',
                    reservation_id TEXT DEFAULT '',
                    tags TEXT DEFAULT '[]',
                    attributes TEXT DEFAULT '{}',
                    boot_commands TEXT DEFAULT '{}',
                    connected_to TEXT DEFAULT '[]',
                    last_seen REAL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS reservations (
                    reservation_id TEXT PRIMARY KEY,
                    device_name TEXT NOT NULL,
                    owner TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    purpose TEXT DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS test_jobs (
                    job_id TEXT PRIMARY KEY,
                    owner TEXT NOT NULL,
                    device_name TEXT NOT NULL,
                    suite_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    passed INTEGER DEFAULT 0,
                    failed INTEGER DEFAULT 0,
                    skipped INTEGER DEFAULT 0,
                    created_at REAL NOT NULL,
                    completed_at REAL DEFAULT 0,
                    details TEXT DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS lab_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )

    @staticmethod
    def _row_to_spec(row: sqlite3.Row) -> DeviceSpec:
        return DeviceSpec(
            name=row["name"],
            board_type=row["board_type"],
            arch=row["arch"],
            ip_address=row["ip_address"],
            mac_address=row["mac_address"],
            subnet=row["subnet"],
            transport=row["transport"],
            transport_config=json.loads(row["transport_config"] or "{}"),
            power_type=row["power_type"],
            power_config=json.loads(row["power_config"] or "{}"),
            bootloader=row["bootloader"],
            cpu=row["cpu"],
            eth_ports=int(row["eth_ports"] or 1),
            deployed_image=row["deployed_image"],
            state=row["state"],
            power_state=row["power_state"],
            owner=row["owner"],
            reservation_id=row["reservation_id"],
            tags=json.loads(row["tags"] or "[]"),
            attributes=json.loads(row["attributes"] or "{}"),
            boot_commands=json.loads(row["boot_commands"] or "{}"),
            connected_to=json.loads(row["connected_to"] or "[]"),
            last_seen=float(row["last_seen"] or 0.0),
        )

    def register_device(self, spec: DeviceSpec | dict[str, Any], overwrite: bool = True) -> DeviceSpec:
        """Insert or update a device in the ResourcePool."""
        if isinstance(spec, dict):
            spec = DeviceSpec.from_dict(spec)
        if not spec.last_seen:
            spec.last_seen = time.time()

        with self._lock, self._conn:
            existing = self.get_device(spec.name)
            if existing is not None and not overwrite:
                return existing
            self._conn.execute(
                """
                INSERT INTO devices (
                    name, board_type, arch, ip_address, mac_address, subnet,
                    transport, transport_config, power_type, power_config,
                    bootloader, cpu, eth_ports, deployed_image, state, power_state,
                    owner, reservation_id, tags, attributes, boot_commands,
                    connected_to, last_seen
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    board_type=excluded.board_type,
                    arch=excluded.arch,
                    ip_address=excluded.ip_address,
                    mac_address=excluded.mac_address,
                    subnet=excluded.subnet,
                    transport=excluded.transport,
                    transport_config=excluded.transport_config,
                    power_type=excluded.power_type,
                    power_config=excluded.power_config,
                    bootloader=excluded.bootloader,
                    cpu=excluded.cpu,
                    eth_ports=excluded.eth_ports,
                    deployed_image=excluded.deployed_image,
                    state=excluded.state,
                    power_state=excluded.power_state,
                    owner=excluded.owner,
                    reservation_id=excluded.reservation_id,
                    tags=excluded.tags,
                    attributes=excluded.attributes,
                    boot_commands=excluded.boot_commands,
                    connected_to=excluded.connected_to,
                    last_seen=excluded.last_seen
                """,
                (
                    spec.name,
                    spec.board_type,
                    spec.arch,
                    spec.ip_address,
                    spec.mac_address,
                    spec.subnet,
                    spec.transport,
                    json.dumps(spec.transport_config),
                    spec.power_type,
                    json.dumps(spec.power_config),
                    spec.bootloader,
                    spec.cpu,
                    spec.eth_ports,
                    spec.deployed_image,
                    spec.state,
                    spec.power_state,
                    spec.owner,
                    spec.reservation_id,
                    json.dumps(spec.tags),
                    json.dumps(spec.attributes),
                    json.dumps(spec.boot_commands),
                    json.dumps(spec.connected_to),
                    spec.last_seen,
                ),
            )
        return spec

    def remove_device(self, name: str) -> bool:
        """Delete a device and any active reservations for it."""
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM reservations WHERE device_name = ?", (name,))
            cur = self._conn.execute("DELETE FROM devices WHERE name = ?", (name,))
            return cur.rowcount > 0

    def _get_device_raw(self, name: str) -> DeviceSpec | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM devices WHERE name = ?", (name,)).fetchone()
            return self._row_to_spec(row) if row else None

    def get_device(self, name: str) -> DeviceSpec | None:
        """Fetch a single DeviceSpec by name."""
        self.expire_stale_reservations()
        return self._get_device_raw(name)

    def list_devices(
        self,
        board_type: str | None = None,
        arch: str | None = None,
        state: str | None = None,
        tags: list[str] | None = None,
        owner: str | None = None,
    ) -> list[DeviceSpec]:
        """List devices matching optional filter criteria."""
        self.expire_stale_reservations()
        query = "SELECT * FROM devices WHERE 1=1"
        params: list[Any] = []
        if board_type:
            query += " AND board_type = ?"
            params.append(board_type)
        if arch:
            query += " AND arch = ?"
            params.append(arch)
        if state:
            query += " AND state = ?"
            params.append(state)
        if owner:
            query += " AND owner = ?"
            params.append(owner)
        query += " ORDER BY name ASC"

        with self._lock:
            rows = self._conn.execute(query, params).fetchall()
        specs = [self._row_to_spec(r) for r in rows]
        if tags:
            required = set(tags)
            specs = [s for s in specs if required.issubset(set(s.tags))]
        return specs

    # Reservation Lifecycle
    def expire_stale_reservations(self) -> int:
        """Automatically release reservations whose TTL has expired."""
        now = time.time()
        with self._lock, self._conn:
            expired_rows = self._conn.execute(
                "SELECT reservation_id, device_name FROM reservations WHERE expires_at < ?",
                (now,),
            ).fetchall()
            for row in expired_rows:
                self._conn.execute(
                    """
                    UPDATE devices
                    SET state = ?, owner = '', reservation_id = ''
                    WHERE name = ? AND reservation_id = ?
                    """,
                    (DeviceState.AVAILABLE.value, row["device_name"], row["reservation_id"]),
                )
                self._conn.execute(
                    "DELETE FROM reservations WHERE reservation_id = ?",
                    (row["reservation_id"],),
                )
            return len(expired_rows)

    def reserve(
        self,
        name: str | None = None,
        board_type: str | None = None,
        arch: str | None = None,
        tags: list[str] | None = None,
        owner: str = "anonymous",
        ttl_seconds: float = 1800.0,
        purpose: str = "",
    ) -> tuple[DeviceSpec, Reservation]:
        """Atomically find and reserve an available device matching the criteria."""
        self.expire_stale_reservations()
        with self._lock, self._conn:
            if name:
                target = self.get_device(name)
                if target is None:
                    raise DeviceNotFoundError(f"Device '{name}' does not exist in the pool")
                if target.state == DeviceState.RESERVED.value and target.owner != owner:
                    raise DeviceBusyError(
                        f"Device '{name}' is already reserved by '{target.owner}' "
                        f"(reservation_id={target.reservation_id})"
                    )
                if target.state not in (DeviceState.AVAILABLE.value, DeviceState.RESERVED.value):
                    raise DeviceBusyError(f"Device '{name}' is in state '{target.state}' and cannot be reserved")
            else:
                candidates = self.list_devices(
                    board_type=board_type,
                    arch=arch,
                    state=DeviceState.AVAILABLE.value,
                    tags=tags,
                )
                if not candidates:
                    raise DeviceNotFoundError(
                        f"No available device matching board_type={board_type!r}, arch={arch!r}, tags={tags!r}"
                    )
                target = candidates[0]

            now = time.time()
            res_id = f"res-{uuid.uuid4().hex[:10]}"
            reservation = Reservation(
                reservation_id=res_id,
                device_name=target.name,
                owner=owner,
                created_at=now,
                expires_at=now + float(ttl_seconds),
                purpose=purpose,
            )
            self._conn.execute("DELETE FROM reservations WHERE device_name = ?", (target.name,))
            self._conn.execute(
                """
                INSERT INTO reservations (reservation_id, device_name, owner, created_at, expires_at, purpose)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    reservation.reservation_id,
                    reservation.device_name,
                    reservation.owner,
                    reservation.created_at,
                    reservation.expires_at,
                    reservation.purpose,
                ),
            )
            self._conn.execute(
                """
                UPDATE devices
                SET state = ?, owner = ?, reservation_id = ?
                WHERE name = ?
                """,
                (DeviceState.RESERVED.value, owner, res_id, target.name),
            )
            updated = self._get_device_raw(target.name)
            assert updated is not None
            return updated, reservation

    def release(self, device_name: str, reservation_id: str | None = None, force: bool = False) -> bool:
        """Release a reserved device and mark it available again."""
        with self._lock, self._conn:
            dev = self.get_device(device_name)
            if dev is None:
                raise DeviceNotFoundError(f"Device '{device_name}' not found")
            if not force and reservation_id and dev.reservation_id and dev.reservation_id != reservation_id:
                raise ReservationError(
                    f"Reservation ID mismatch for '{device_name}': expected {dev.reservation_id}, got {reservation_id}"
                )
            self._conn.execute("DELETE FROM reservations WHERE device_name = ?", (device_name,))
            self._conn.execute(
                """
                UPDATE devices
                SET state = ?, owner = '', reservation_id = ''
                WHERE name = ?
                """,
                (DeviceState.AVAILABLE.value, device_name),
            )
            return True

    def list_reservations(self, owner: str | None = None) -> list[Reservation]:
        """Return all active reservations."""
        self.expire_stale_reservations()
        query = "SELECT * FROM reservations"
        params: list[Any] = []
        if owner:
            query += " WHERE owner = ?"
            params.append(owner)
        query += " ORDER BY created_at DESC"
        with self._lock:
            rows = self._conn.execute(query, params).fetchall()
        return [
            Reservation(
                reservation_id=r["reservation_id"],
                device_name=r["device_name"],
                owner=r["owner"],
                created_at=float(r["created_at"]),
                expires_at=float(r["expires_at"]),
                purpose=r["purpose"],
            )
            for r in rows
        ]

    # Test Jobs History
    def record_test_job(
        self,
        device_name: str,
        suite_name: str,
        status: str,
        owner: str = "admin",
        passed: int = 0,
        failed: int = 0,
        skipped: int = 0,
        details: dict[str, Any] | None = None,
        job_id: str | None = None,
    ) -> dict[str, Any]:
        """Store a test job execution record in SQLite."""
        jid = job_id or f"job-{uuid.uuid4().hex[:8]}"
        now = time.time()
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO test_jobs
                (job_id, owner, device_name, suite_name, status, passed, failed, skipped, created_at, completed_at, details)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    jid,
                    owner,
                    device_name,
                    suite_name,
                    status,
                    passed,
                    failed,
                    skipped,
                    now,
                    now if status in ("COMPLETED", "PASS", "FAIL") else 0.0,
                    json.dumps(details or {}),
                ),
            )
        return {
            "job_id": jid,
            "owner": owner,
            "device_name": device_name,
            "suite_name": suite_name,
            "status": status,
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "created_at": now,
            "details": details or {},
        }

    def list_test_jobs(self, owner: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        query = "SELECT * FROM test_jobs"
        params: list[Any] = []
        if owner:
            query += " WHERE owner = ?"
            params.append(owner)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with self._lock:
            rows = self._conn.execute(query, params).fetchall()
        return [
            {
                "job_id": r["job_id"],
                "owner": r["owner"],
                "device_name": r["device_name"],
                "suite_name": r["suite_name"],
                "status": r["status"],
                "passed": r["passed"],
                "failed": r["failed"],
                "skipped": r["skipped"],
                "created_at": r["created_at"],
                "completed_at": r["completed_at"],
                "details": json.loads(r["details"] or "{}"),
            }
            for r in rows
        ]

    # Lab Settings (for First-Run Wizard & Global Settings)
    def get_settings(self) -> dict[str, Any]:
        with self._lock:
            rows = self._conn.execute("SELECT key, value FROM lab_settings").fetchall()
        settings = {
            "lab_name": "DAMF Embedded Hardware Lab",
            "lab_scope": "R&D / Automated HIL Verification",
            "primary_subnet": "192.168.10.0/24",
            "additional_subnets": ["192.168.20.0/24", "10.0.50.0/24"],
            "admin_name": "Lab Administrator",
            "admin_email": "admin@damf.local",
            "ldap_enabled": False,
            "smtp_server": "smtp.damf.local",
        }
        for r in rows:
            try:
                settings[r["key"]] = json.loads(r["value"])
            except ValueError:
                settings[r["key"]] = r["value"]
        return settings

    def update_settings(self, new_settings: dict[str, Any]) -> dict[str, Any]:
        with self._lock, self._conn:
            for k, v in new_settings.items():
                self._conn.execute(
                    "INSERT OR REPLACE INTO lab_settings (key, value) VALUES (?, ?)",
                    (k, json.dumps(v)),
                )
        return self.get_settings()

    # Board file loader & Legacy Compatibility API
    def load_board_files(self, folder_path: str | Path) -> list[str]:
        """Load YAML board profiles from a directory."""
        folder = Path(folder_path)
        if not folder.exists():
            return []
        loaded_types: list[str] = []
        for yml_file in sorted(folder.glob("*.y*ml")):
            board_type = yml_file.stem
            loaded_types.append(board_type)
            docs = safe_load_all_yaml(yml_file.read_text(encoding="utf-8"))
            boot_cmds: dict[str, list[str]] = {}
            attrs: dict[str, Any] = {}
            for doc in docs:
                if not isinstance(doc, dict):
                    continue
                if "commands" in doc and isinstance(doc["commands"], dict):
                    for k, v in doc["commands"].items():
                        if isinstance(v, list):
                            boot_cmds[k] = [str(x) for x in v]
                if "attributes" in doc and isinstance(doc["attributes"], dict):
                    attrs.update(doc["attributes"])
            if not boot_cmds and not attrs:
                continue
            loaded_types.append(board_type)
            existing = self.list_devices(board_type=board_type)
            if not existing:
                self.register_device(
                    DeviceSpec(
                        name=f"{board_type}-01",
                        board_type=board_type,
                        arch=str(attrs.get("arch", "arm64")),
                        attributes=attrs,
                        boot_commands=boot_cmds,
                    )
                )
        return loaded_types

    @property
    def available_boards(self) -> dict[str, dict[str, Any]]:
        return {d.name: d.to_dict() for d in self.list_devices(state=DeviceState.AVAILABLE.value)}

    @property
    def board_types(self) -> list[str]:
        return sorted({d.board_type for d in self.list_devices()})

    def get_board_by_type(self, board_type: str) -> str:
        """Legacy helper: return the name of the first available board of `board_type`."""
        matches = self.list_devices(board_type=board_type, state=DeviceState.AVAILABLE.value)
        if not matches:
            all_matches = self.list_devices(board_type=board_type)
            if not all_matches:
                raise DeviceNotFoundError(f"No board of type '{board_type}' found in ResourcePool")
            return all_matches[0].name
        return matches[0].name

    def find_available_boards(self) -> list[str]:
        return [d.name for d in self.list_devices(state=DeviceState.AVAILABLE.value)]

    def find_board_types(self) -> list[str]:
        types = self.board_types
        self.logger.info("Done reading available board types: %s", types)
        return types

    def seed_demo_devices(self) -> list[DeviceSpec]:
        """Seed representative lab devices (Raspberry Pi, TI Sitara, BeagleBone, Android) if empty."""
        if self.list_devices():
            return self.list_devices()
        demo_specs = [
            DeviceSpec(
                name="rpi4-lab-01",
                board_type="raspberry-pi-4",
                arch="arm64",
                ip_address="192.168.10.101",
                mac_address="DC:A6:32:1A:2B:01",
                subnet="192.168.10.0/24",
                transport="ssh",
                transport_config={"user": "root", "simulated": True},
                power_type="simulated",
                bootloader="u-boot",
                cpu="Broadcom BCM2711 Cortex-A72",
                deployed_image="Raspbian Bookworm 64-bit",
                state=DeviceState.AVAILABLE.value,
                power_state="on",
                tags=["gpio", "i2c", "spi", "raspberry-pi", "hil-rack-1"],
                connected_to=["ti-am62x-evm-01"],
            ),
            DeviceSpec(
                name="rpi5-lab-02",
                board_type="raspberry-pi-5",
                arch="arm64",
                ip_address="192.168.10.102",
                mac_address="2C:CF:67:44:11:09",
                subnet="192.168.10.0/24",
                transport="ssh",
                transport_config={"user": "root", "simulated": True},
                power_type="simulated",
                bootloader="u-boot",
                cpu="Broadcom BCM2712 Cortex-A76",
                deployed_image="Focused Linux 6.6 LTS",
                state=DeviceState.AVAILABLE.value,
                power_state="on",
                tags=["pcie", "gpio", "raspberry-pi", "hil-rack-1"],
            ),
            DeviceSpec(
                name="ti-am62x-evm-01",
                board_type="ti-am62x",
                arch="arm64",
                ip_address="192.168.10.115",
                mac_address="D0:FF:50:88:31:20",
                subnet="192.168.10.0/24",
                transport="serial",
                transport_config={"port": "/dev/ttyUSB0", "baudrate": 115200, "simulated": True},
                power_type="simulated",
                bootloader="u-boot",
                cpu="TI Sitara AM6254 Quad Cortex-A53",
                deployed_image="TI Processor SDK Linux 09.02",
                state=DeviceState.AVAILABLE.value,
                power_state="on",
                tags=["ti", "can-bus", "industrial", "uboot", "hil-rack-1"],
                connected_to=["rpi4-lab-01", "beaglebone-black-01"],
                boot_commands={
                    "ramdisk_boot": [
                        "setenv ipaddr 192.168.10.115",
                        "tftp 0x82000000 {IMAGE}",
                        "tftp 0x88000000 {DTB}",
                        "tftp 0x88080000 {ROOT_FS}",
                        "booti 0x82000000 0x88080000 0x88000000",
                    ]
                },
            ),
            DeviceSpec(
                name="beaglebone-black-01",
                board_type="beaglebone-black",
                arch="arm",
                ip_address="192.168.20.55",
                mac_address="04:A3:16:90:12:4F",
                subnet="192.168.20.0/24",
                transport="ssh",
                transport_config={"user": "debian", "simulated": True},
                power_type="simulated",
                bootloader="u-boot",
                cpu="TI Sitara AM3358 Cortex-A8",
                deployed_image="Debian 12 IoT",
                state=DeviceState.AVAILABLE.value,
                power_state="off",
                tags=["ti", "pru", "gpio", "hil-rack-2"],
                connected_to=["ti-am62x-evm-01"],
            ),
            DeviceSpec(
                name="pixel-7-testphone",
                board_type="android",
                arch="arm64",
                ip_address="10.0.50.21",
                mac_address="3C:5A:B4:77:88:99",
                subnet="10.0.50.0/24",
                transport="adb",
                transport_config={"serial": "10.0.50.21:5555", "simulated": True},
                power_type="simulated",
                bootloader="fastboot",
                cpu="Google Tensor G2",
                deployed_image="Android 15 AOSP userdebug",
                state=DeviceState.AVAILABLE.value,
                power_state="on",
                tags=["android", "adb", "ble", "wifi-test"],
                connected_to=["rpi4-lab-01"],
            ),
        ]
        for spec in demo_specs:
            self.register_device(spec)
        return self.list_devices()
