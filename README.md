# Device Automation & Management Framework (DAMF)

## Purpose
This framework is aimed at embedded software developers, software testers and lab admins and it strives to provide a unified way of working with the boards available for automated testing (Raspberry Pi, Texas Instruments Sitara/AM335x/AM62x/BeagleBone, Linux SBCs, and Android devices).

From board lab management tasks and network auto-discovery to board access provisioning (viewing each board/device as a resource that can be dynamically allocated from a pool of resources) and test automation, DAMF acts as the layer between the hardware lab and test automation scripts.

---

## Architecture & Features (v2.0)

1. **Importable Python SDK (`damf`)**:
   - Clean, context-managed `Lab` and `Device` APIs (`with lab.acquire(board_type="raspberry-pi-4") as dev:`) that automatically lock/reserve boards and release them when tests complete.
   - Multi-node cluster acquisition (`with lab.acquire_cluster({"master": ..., "dut": ...}) as cluster:`).
   - Zero mandatory third-party dependencies for core functionality (works out-of-the-box with Python's standard library, with optional extras for `PyYAML`, `pyserial`, `Flask`, and `pytest`).
2. **Composable Transports & Power Controllers**:
   - **Transports**: `SSHTransport` (OpenSSH/Dropbear), `SerialTransport` (UART + U-Boot command templating `{IMAGE}`, `{DTB}`, `{ROOT_FS}`), `ADBTransport` (Android Debug Bridge over USB or Wi-Fi), and `LocalTransport`.
   - **Power Controllers**: `WebhookPowerController` (Shelly/Tasmota/REST smart plugs), `USBHubPowerController` (`uhubctl` USB port power), `IPMIPowerController` (`ipmitool`), `CommandPowerController`, and `SimulatedPowerController`.
3. **Network & Local Bus Discovery (`damf.discovery`)**:
   - `ARPScanner` with built-in MAC OUI vendor detection for Raspberry Pi Foundation, Texas Instruments, BeagleBoard, Espressif, NVIDIA Jetson, Arduino, and Google/Android.
   - `MDNSScanner` for `.local` hostnames, `SubnetScanner` for SSH/ADB port probing, `SerialScanner` for `/dev/ttyUSB*` & `/dev/ttyACM*`, and `ADBScanner` for `adb devices -l`.
4. **SQLite-Backed Resource Pool, JUnit Result Parser & Pytest Plugin**:
   - Persistent inventory, atomic reservation locking with TTL lease expiration, and JUnit XML / JSON test report generation.
   - Built-in `pytest` fixtures (`damf_lab`, `damf_device`).
5. **Interactive Web Dashboard & REST API (`damf.web`)**:
   - **Dashboard**: Real-time KPIs, active reservations, and quick command/test runner.
   - **Devices Manager**: Add, edit, delete, export YAML/JSON, reserve/release, and toggle board power.
   - **Dynamic Lab Topology View**: Interactive SVG network/subnet diagram displaying boards and inter-device links (`connected_to`).
   - **Setup Wizard**: Configure lab name, subnets, and administrator settings.

---

## Quick Start

### 1. Python API Usage in Test Scripts
```python
from damf import Lab

# Initialize lab (from SQLite DB, config file, or live network discovery)
lab = Lab(db_path="~/.damf/damf.db", seed_demo=True)

# Reserve a Raspberry Pi 4, power it on, run commands, and auto-release on exit
with lab.acquire(board_type="raspberry-pi-4", tags=["gpio"], owner="ci-runner") as rpi:
    rpi.power_on()
    res = rpi.run("uname -a", check=True)
    print(res.stdout)

    suite = lab.run_test_suite(
        rpi,
        commands={
            "check_kernel": "uname -r",
            "check_i2c_dev": "ls /dev",
        },
        suite_name="rpi_sanity",
        output_dir="./reports",
    )
    assert suite.failed == 0
```

### 2. CLI Usage
```bash
# List devices (seeding demo Raspberry Pi, TI AM62x, BeagleBone, and Android devices)
python3 -m damf.cli --seed-demo devices

# Discover devices over ARP, mDNS, USB Serial, and ADB
python3 -m damf.cli discover --mdns

# Reserve, execute a command, and release a board
python3 -m damf.cli reserve --name rpi4-lab-01 --owner tester
python3 -m damf.cli exec rpi4-lab-01 "uname -a"
python3 -m damf.cli release rpi4-lab-01

# Launch the interactive Web UI & REST API server on http://127.0.0.1:8080
python3 -m damf.cli serve --port 8080
# (or via python3 damf-ui.py)
```

### 3. Running the Test Suite
```bash
python3 -m unittest discover -s tests -v
```
