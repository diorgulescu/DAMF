# Device Automation & Management Framework (DAMF)

## Purpose
DAMF is designed for embedded software developers, QA/test engineers, and hardware lab administrators who need a unified way to discover, manage, monitor, and automate development boards and embedded targets—such as **Raspberry Pi**, **Texas Instruments** (Sitara AM335x / AM62x / AM64x, BeagleBone, BeaglePlay), **Linux/Unix SBCs**, and **Android** devices.

From network/USB/ADB auto-discovery and interactive topology management to resource reservation locking, live target telemetry, fleet-wide content deployment, and automated test execution, DAMF acts as both a **lab administration platform** and an **importable Python SDK** for test scripts.

---

## Architecture & Key Capabilities (v2.0)

1. **Importable Python SDK (`damf`) & Remote Client (`RemoteLabClient`)**
   - Context-managed `Lab` and `Device` APIs (`with lab.acquire(board_type="raspberry-pi-4") as dev:`) that automatically reserve/lock boards from the pool and release them when tests complete.
   - Atomic multi-node cluster acquisition (`with lab.acquire_cluster({"master": ..., "dut": ...}) as cluster:`).
   - `RemoteLabClient` with matching methods for test scripts running against a remote DAMF server over HTTP REST.
   - **Zero mandatory external dependencies**: works out of the box with Python's standard library (`sqlite3`, `urllib`, `http.server`, `termios`), with optional extras for `PyYAML`, `pyserial`, `Flask`, and `pytest`.

2. **Composable Transports (`damf.transports`) & Dual-Transport Support**
   - **`SSHTransport`**: Non-interactive OpenSSH/Dropbear command execution (`BatchMode=yes`), `scp` file transfers, interactive CLI builder, and automatic target OS/init-system probing.
   - **`SerialTransport`**: UART console access (`/dev/ttyUSB*`, `/dev/ttyACM*`, `/dev/cu.*`) using `pyserial` or a built-in zero-dependency POSIX `termios` 8N1 implementation, console state detection (`shell`, `login`, `uboot`), U-Boot command templating (`{IMAGE}`, `{DTB}`, `{ROOT_FS}`), and interactive terminal integration (`picocom`, `tio`, `minicom`, `screen`, `miniterm`).
   - **Dual Transport**: Boards whose primary transport is `ssh` can simultaneously configure a secondary `serial_port` and use `connect_serial()` / `run_serial()` for out-of-band UART access.
   - **`ADBTransport`**: Android Debug Bridge over USB or Wi-Fi (`adb shell`, `adb push`, `adb pull`, `adb reboot`, `logcat`).
   - **`LocalTransport`**: Local subprocess and filesystem execution for self-tests and host runner nodes.

3. **Context-Aware OS Detection & Power Control (`damf.power`)**
   - **`SSHPowerController`**: Probes the target OS (`/etc/os-release`, `uname -s`, PID 1 init system, and `/sbin/reboot` symlink) to issue the right reboot command for **systemd** (Debian/Ubuntu/Raspbian), **BusyBox** (Buildroot/minimal embedded), **SysVinit** (Yocto/Poky), **OpenRC** (Alpine), or **BSD/Darwin**, automatically prefixing `sudo -n` when connected as a non-root user.
   - Hardware power controllers: `WebhookPowerController` (Shelly/Tasmota/REST smart plugs), `USBHubPowerController` (`uhubctl`), `IPMIPowerController` (`ipmitool`), `CommandPowerController`, and `SimulatedPowerController`.

4. **Two-Tier Target Heartbeat & Telemetry Agent (`damf.agent`)**
   - **Tier 1 (Python 3 stdlib daemon)**: Deployed to `/tmp/damf_agent.py` over SSH on targets with Python 3.
   - **Tier 2 (POSIX `/bin/sh` + `wget`/`curl` daemon)**: Automatically generated and deployed to `/tmp/damf_agent.sh` for minimal BusyBox/Buildroot targets without Python.
   - Pushes periodic heartbeats to `POST /api/v1/agent/heartbeat` with **1m/5m/15m CPU load**, **RAM & disk usage**, **SoC temperature** (`/sys/class/thermal/...`), **uptime**, and **recent kernel/system logs**, with automatic stale-agent offline detection (`check_agent_health()`).

5. **On-Demand System Log Collection & Fleet-Wide Content Deployment**
   - **On-Demand Logs (`copy_system_logs`)**: Collects and bundles `dmesg`, `journalctl`, `/var/log/syslog`, `/var/log/messages` (or Android `logcat` + `dmesg`), plus any custom remote log files into timestamped local `.log` bundles or direct browser downloads.
   - **Single & Fleet Deployment (`deploy_to_device` / `deploy_to_lab`)**: Deploy a single file, folder tree, archive (`.tar.gz`, `.tgz`, `.tar`, `.zip` with automatic remote extraction), inline file content, or JSON folder structure (`{"bin/run.sh": "..."}`) to one target or concurrently across all lab targets in a single procedure, with optional `chmod` and post-deploy commands.

6. **Network & Local Bus Auto-Discovery (`damf.discovery`)**
   - `ARPScanner` with MAC OUI vendor detection (Raspberry Pi Foundation, Texas Instruments, BeagleBoard, Espressif, NVIDIA Jetson, Arduino, Google/Android).
   - `MDNSScanner` (`.local`), `SubnetScanner` (SSH/ADB port probing), `SerialScanner` (`/dev/ttyUSB*`, `/dev/ttyACM*`), and `ADBScanner` (`adb devices -l`).

7. **Interactive Web UI & REST API (`damf.web`)**
   - Single-page administrative interface featuring **Dashboard**, **Managed Devices**, **Dynamic Lab Topology SVG View** (with interactive Node Inspector), **Test Jobs History**, and **Setup Wizard**.

---

## Quick Start

### 1. Python SDK Usage in Test & Automation Scripts

```python
from damf import Lab

# Initialize lab (backed by SQLite DB, YAML/JSON config, or in-memory with demo devices)
lab = Lab(db_path="~/.damf/damf.db", seed_demo=True)

# 1. Manually define a device in the lab topology (with both SSH and UART Serial configured)
lab.define_device(
    name="beagleplay-01",
    board_type="ti-am62x",
    ip_address="192.168.10.188",
    ssh_user="debian",
    os_hint="debian",
    serial_port="/dev/ttyUSB2",
    baudrate=115200,
    connected_to=["rpi4-lab-01"],
    tags=["ti", "can-bus", "uart"],
    simulated=True,
)

# 2. Connect via SSH (auto-detects OS/init system) & connect via Serial (detects shell/login/uboot)
ssh_info = lab.connect_ssh("beagleplay-01")
serial_info = lab.connect_serial("beagleplay-01")
serial_cmd = lab.run_serial("beagleplay-01", "uname -a")

# 3. Deploy the heartbeat/telemetry agent & query vital load/RAM/temperature/logs
lab.deploy_agent("beagleplay-01", server_url="http://192.168.10.1:8080", interval=15)
telemetry = lab.get_telemetry("beagleplay-01", refresh=True)

# 4. Copy system logs on demand to a local folder
log_bundle = lab.copy_system_logs("beagleplay-01", output_dir="./logs", max_lines=200)

# 5. Deploy a folder structure, archive (.tar.gz/.zip), or file across all online lab targets
fleet_report = lab.deploy_to_lab(
    remote_path="/opt/damf_toolkit",
    structure={
        "bin/env_check.sh": "#!/bin/sh\nuname -a\n",
        "conf/settings.ini": "mode=hil\n",
    },
    chmod="755",
    post_deploy_cmd="sh /opt/damf_toolkit/bin/env_check.sh",
)

# 6. Context-aware Linux/Unix reboot over SSH
lab.reboot_device("beagleplay-01", via_ssh=True)

# 7. Reserve a board for automated testing and auto-release on exit
with lab.acquire(board_type="raspberry-pi-4", tags=["gpio"], owner="ci-runner") as rpi:
    rpi.power_on()
    res = rpi.run("uname -a", check=True)
    suite = lab.run_test_suite(
        rpi,
        commands={"check_kernel": "uname -r", "check_dev": "ls /dev"},
        suite_name="rpi_sanity",
        output_dir="./reports",
    )
    assert suite.failed == 0

lab.close()
```

---

### 2. CLI Reference (`damf`)

```bash
# List registered devices in the pool
python3 -m damf.cli --seed-demo devices

# Manually define/add a device in the lab topology (with SSH + optional Serial port)
python3 -m damf.cli add-device ti-evm-02 --ip 192.168.10.120 --type ti-am62x \
    --user root --os poky --serial-port /dev/ttyUSB0 --baudrate 115200 \
    --connect-to rpi4-lab-01 --simulated

# Link two existing devices in the lab topology
python3 -m damf.cli link ti-evm-02 beaglebone-black-01

# Connect via SSH (probe OS & show interactive command, or run -c <cmd>, or -i interactive)
python3 -m damf.cli --seed-demo ssh rpi4-lab-01
python3 -m damf.cli --seed-demo ssh rpi4-lab-01 -c "uname -a"

# Connect via Serial / UART (probe console state & OS, run -c <cmd>, or -i interactive terminal)
python3 -m damf.cli --seed-demo serial ti-am62x-evm-01
python3 -m damf.cli --seed-demo serial rpi4-lab-01 -c "uname -a"

# Reboot a target over SSH using the OS-appropriate Linux/Unix reboot command
python3 -m damf.cli --seed-demo reboot rpi4-lab-01

# Deploy the heartbeat/telemetry agent over SSH & inspect vital telemetry
python3 -m damf.cli --seed-demo deploy-agent rpi4-lab-01 --server http://127.0.0.1:8080
python3 -m damf.cli --seed-demo telemetry rpi4-lab-01 --refresh

# Copy system/kernel logs on demand from a target board
python3 -m damf.cli --seed-demo copy-logs rpi4-lab-01 -o ./logs -n 200

# Deploy a local file, folder, archive (.tar.gz/.zip), or inline content to all lab targets
python3 -m damf.cli --seed-demo deploy --all --dest /opt/lab_toolkit \
    --content "#!/bin/sh\necho ready" --filename init.sh --chmod 755

# Auto-discover boards over ARP, mDNS, USB Serial, and ADB
python3 -m damf.cli discover --mdns

# Reserve, execute a command, and release a board
python3 -m damf.cli reserve --name rpi4-lab-01 --owner tester
python3 -m damf.cli exec rpi4-lab-01 "uname -a"
python3 -m damf.cli release rpi4-lab-01

# Start the interactive Web UI & REST API server on http://127.0.0.1:8080
python3 -m damf.cli serve --port 8080
# (or run `python3 damf-ui.py`)
```

---

### 3. REST API v1 Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/v1/status` | Pool KPIs (total, available, reserved boards, jobs count) |
| `GET`, `POST` | `/api/v1/devices` | List devices (with filters) or define/register a device |
| `GET`, `PUT`, `DELETE` | `/api/v1/devices/<name>` | Inspect, update, or delete a specific device |
| `POST` | `/api/v1/devices/<name>/reserve` | Atomically reserve a device with TTL lease |
| `POST` | `/api/v1/devices/<name>/release` | Release a device reservation |
| `POST` | `/api/v1/devices/<name>/connect` | Connect via SSH and detect target OS & init system |
| `POST` | `/api/v1/devices/<name>/serial-connect` | Connect via Serial (UART) and detect console state (`shell`/`login`/`uboot`) |
| `POST` | `/api/v1/devices/<name>/serial-exec` | Execute a command over the target's Serial (UART) console |
| `POST` | `/api/v1/devices/<name>/reboot` | Context-aware Linux/Unix reboot over SSH |
| `POST` | `/api/v1/devices/<name>/power` | Power control (`on`, `off`, `reboot`) |
| `POST` | `/api/v1/devices/<name>/exec` | Run a command over the device's primary transport |
| `POST` | `/api/v1/devices/<name>/deploy-agent` | Deploy the Tier-1 (Python) or Tier-2 (POSIX `sh`) heartbeat agent |
| `GET` | `/api/v1/devices/<name>/telemetry` | Retrieve CPU load, RAM, disk, SoC temp, uptime, and recent logs |
| `GET`, `POST` | `/api/v1/devices/<name>/logs` | Copy system logs on demand (or `?format=download` for raw `.log`) |
| `POST` | `/api/v1/devices/<name>/deploy` | Deploy file, folder, archive, or content to a single target |
| `POST` | `/api/v1/deploy` | Broadcast deploy file, folder structure, or archive across lab targets |
| `POST` | `/api/v1/agent/heartbeat` | Ingest periodic heartbeat & telemetry payload from target agent |
| `POST` | `/api/v1/agent/check-health` | Mark stale agent-monitored devices as `offline` |
| `GET` | `/api/v1/topology` | Retrieve subnet groups, devices, and bidirectional topology links |
| `POST`, `DELETE` | `/api/v1/topology/links` | Link or unlink two devices in the lab topology |
| `POST` | `/api/v1/discover` | Trigger ARP, mDNS, Subnet, Serial, and ADB discovery |
| `GET`, `POST` | `/api/v1/jobs` | List executed test jobs or trigger a new test suite |

---

### 4. Running the Test Suite
```bash
python3 -m unittest discover -s tests -v
```
