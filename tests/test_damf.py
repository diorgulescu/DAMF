"""Comprehensive unit and integration tests for DAMF v2.0 (Steps 1 through 5)."""

from __future__ import annotations

from pathlib import Path
import tempfile
import threading
import time
import unittest
import xml.etree.ElementTree as ET

import damf
from damf import (
    ADBScanner,
    ARPScanner,
    CommandResult,
    DAMFWebApp,
    Device,
    DeviceBusyError,
    DeviceNotFoundError,
    DeviceSpec,
    DiscoveryEngine,
    Lab,
    MDNSScanner,
    RemoteLabClient,
    ResourcePool,
    ResultParser,
    SerialScanner,
    create_http_server,
    dump_yaml,
    lookup_mac_vendor,
    normalize_mac,
    safe_load_yaml,
)
from damf.cli import main as cli_main


class TestStep1SDKAndConfig(unittest.TestCase):
    """Step 1: Package structure, models, and YAML/JSON config parsing."""

    def test_yaml_roundtrip_and_parsing(self) -> None:
        sample = """
        workspace:
          root_path: /tmp/damf_
          logs_dir: logs
        devices:
          - name: rpi4-01
            board_type: raspberry-pi-4
            arch: arm64
            tags: [gpio, i2c]
        """
        parsed = safe_load_yaml(sample)
        self.assertEqual(parsed["workspace"]["logs_dir"], "logs")
        self.assertEqual(parsed["devices"][0]["name"], "rpi4-01")
        self.assertEqual(parsed["devices"][0]["tags"], ["gpio", "i2c"])

        dumped = dump_yaml(parsed)
        reparsed = safe_load_yaml(dumped)
        self.assertEqual(reparsed["workspace"]["logs_dir"], "logs")

    def test_device_spec_and_command_result(self) -> None:
        spec = DeviceSpec.from_dict(
            {
                "name": "ti-board-1",
                "board_type": "ti-am62x",
                "arch": "arm64",
                "unknown_extra_field": "ignored",
            }
        )
        self.assertEqual(spec.name, "ti-board-1")
        self.assertEqual(spec.board_type, "ti-am62x")

        ok_res = CommandResult(command="uname -a", returncode=0, stdout="Linux\n", device_name="ti-board-1")
        self.assertTrue(ok_res.ok)
        self.assertIs(ok_res.check(), ok_res)

        fail_res = CommandResult(command="false", returncode=1, stderr="err", device_name="ti-board-1")
        self.assertFalse(fail_res.ok)
        with self.assertRaises(RuntimeError):
            fail_res.check()


class TestStep2TransportsAndPower(unittest.TestCase):
    """Step 2: Composable Transports (SSH, Serial/U-Boot, ADB, Local) and Power Controllers."""

    def test_local_transport_execution_and_file_transfer(self) -> None:
        spec = DeviceSpec(name="host-runner", transport="local", power_type="simulated")
        dev = Device(spec)
        dev.connect()
        dev.power_on()
        self.assertEqual(dev.power_state, "on")

        res = dev.run("echo hello_damf", env={"MY_VAR": "42"})
        self.assertTrue(res.ok)
        self.assertIn("hello_damf", res.stdout)

        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "src.txt"
            dst = Path(tmpdir) / "dst.txt"
            src.write_text("payload-123", encoding="utf-8")
            dev.upload(src, str(dst))
            self.assertEqual(dst.read_text(encoding="utf-8"), "payload-123")

        dev.power_off()
        self.assertEqual(dev.power_state, "off")
        dev.disconnect()

    def test_serial_transport_and_uboot_templating(self) -> None:
        spec = DeviceSpec(
            name="ti-am335x-01",
            board_type="ti-am335x",
            transport="serial",
            transport_config={"port": "/dev/ttyUSB0", "baudrate": 115200, "simulated": True},
            boot_commands={
                "ramdisk_boot": [
                    "tftp 0x82000000 {IMAGE}",
                    "tftp 0x88000000 {DTB}",
                    "tftp 0x88080000 {ROOT_FS}",
                ]
            },
        )
        dev = Device(spec)
        dev.connect()
        rendered = dev.boot_bootloader(
            "ramdisk",
            {"image": "Image.gz", "dtb": "am335x-evm.dtb", "root_fs": "initramfs.cpio"},
        )
        self.assertEqual(
            rendered,
            [
                "tftp 0x82000000 Image.gz",
                "tftp 0x88000000 am335x-evm.dtb",
                "tftp 0x88080000 initramfs.cpio",
            ],
        )

    def test_adb_simulated_transport(self) -> None:
        spec = DeviceSpec(
            name="pixel-8",
            board_type="android",
            transport="adb",
            transport_config={"serial": "emulator-5554", "simulated": True},
        )
        dev = Device(spec)
        dev.connect()
        res = dev.run("getprop ro.product.model")
        self.assertTrue(res.ok)
        self.assertIn("emulator-5554", res.stdout)


class TestStep3Discovery(unittest.TestCase):
    """Step 3: Network (ARP/OUI, mDNS), USB/Serial, and ADB device discovery."""

    def test_mac_oui_lookup(self) -> None:
        self.assertEqual(normalize_mac("dc:a6:32:1:2:b"), "DC:A6:32:01:02:0B")
        rpi_vendor = lookup_mac_vendor("dc:a6:32:1:2:b")
        self.assertIsNotNone(rpi_vendor)
        assert rpi_vendor is not None
        self.assertEqual(rpi_vendor[1], "raspberry-pi-4")

        ti_vendor = lookup_mac_vendor("d0:ff:50:aa:bb:cc")
        self.assertIsNotNone(ti_vendor)
        assert ti_vendor is not None
        self.assertEqual(ti_vendor[1], "ti-am62x")

    def test_arp_adb_mdns_serial_scanners_and_deduplication(self) -> None:
        arp_text = """
        rpi4-node.local (192.168.10.50) at dc:a6:32:11:22:33 on en0 ifscope [ethernet]
        ? (192.168.10.60) at d0:ff:50:44:55:66 on en0 ifscope [ethernet]
        router.local (192.168.10.1) at 11:22:33:44:55:66 on en0 ifscope [ethernet]
        """
        arp_devs = ARPScanner().scan(arp_output=arp_text, only_known_vendors=True)
        self.assertEqual(len(arp_devs), 2)
        self.assertEqual(arp_devs[0].board_type, "raspberry-pi-4")
        self.assertEqual(arp_devs[1].board_type, "ti-am62x")

        adb_text = """List of devices attached
        192.168.10.99:5555     device product:panther model:Pixel_7 device:panther transport_id:3
        """
        adb_devs = ADBScanner().scan(adb_output=adb_text)
        self.assertEqual(len(adb_devs), 1)
        self.assertEqual(adb_devs[0].board_type, "android")
        self.assertEqual(adb_devs[0].ip_address, "192.168.10.99")

        mdns_devs = MDNSScanner().scan(
            candidate_hosts=[("raspberrypi.local", "raspberry-pi-4", "arm64")],
            resolver=lambda host: "192.168.10.50",
        )
        self.assertEqual(len(mdns_devs), 1)

        serial_devs = SerialScanner().scan(custom_ports=["/dev/ttyUSB0"])
        self.assertEqual(len(serial_devs), 1)
        self.assertEqual(serial_devs[0].transport, "serial")

        # Deduplicate ARP + mDNS sharing 192.168.10.50
        merged = DiscoveryEngine.deduplicate(arp_devs + mdns_devs + adb_devs + serial_devs)
        self.assertEqual(len(merged), 4)


class TestStep4PoolLabAndResults(unittest.TestCase):
    """Step 4: SQLite ResourcePool reservations, Lab context manager API, and JUnit ResultParser."""

    def test_lab_acquire_release_and_conflict(self) -> None:
        lab = Lab(db_path=":memory:", seed_demo=True)
        self.assertGreaterEqual(len(lab.devices()), 5)

        with lab.acquire(board_type="raspberry-pi-4", owner="tester-1") as dev:
            self.assertEqual(dev.board_type, "raspberry-pi-4")
            # Attempting to reserve the same device by another user raises DeviceBusyError
            with self.assertRaises(DeviceBusyError):
                lab.pool.reserve(name=dev.name, owner="tester-2")

            suite = lab.run_test_suite(dev, commands={"check_uname": "uname -a"}, suite_name="smoke")
            self.assertEqual(suite.passed, 1)
            self.assertEqual(suite.failed, 0)

        # After exiting the `with` block, the device is automatically released
        spec_after = lab.pool.get_device(dev.name)
        assert spec_after is not None
        self.assertEqual(spec_after.state, "available")
        self.assertEqual(spec_after.owner, "")

    def test_cluster_acquisition_and_ttl_expiry(self) -> None:
        lab = Lab(db_path=":memory:", seed_demo=True)
        with lab.acquire_cluster(
            {
                "master": {"board_type": "raspberry-pi-4"},
                "dut": {"board_type": "ti-am62x"},
            },
            owner="cluster-job",
        ) as cluster:
            self.assertIn("master", cluster)
            self.assertIn("dut", cluster)
            self.assertEqual(cluster["dut"].board_type, "ti-am62x")

        # Verify TTL expiration
        spec, _ = lab.pool.reserve(name="rpi4-lab-01", owner="temp-user", ttl_seconds=-1.0)
        self.assertEqual(lab.pool.expire_stale_reservations(), 1)
        refreshed = lab.pool.get_device(spec.name)
        assert refreshed is not None
        self.assertEqual(refreshed.state, "available")

    def test_result_parser_junit_xml(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            raw_file = Path(tmpdir) / "gpio_suite_test_result"
            raw_file.write_text("pin_toggle: PASS\ni2c_bus: FAIL\nspi_loop: SKIP\n", encoding="utf-8")

            parser = ResultParser(tmpdir, tmpdir)
            written = parser.process_test_results()
            self.assertEqual(len(written), 1)

            tree = ET.parse(written[0])
            root = tree.getroot()
            suite_el = root.find("testsuite")
            assert suite_el is not None
            self.assertEqual(suite_el.attrib["name"], "gpio_suite")
            self.assertEqual(suite_el.attrib["tests"], "3")
            self.assertEqual(suite_el.attrib["failures"], "1")
            self.assertEqual(suite_el.attrib["skipped"], "1")


class TestStep5WebServerCLIAndLegacy(unittest.TestCase):
    """Step 5: Web UI, REST API server, RemoteLabClient, CLI, and Legacy module compatibility."""

    def test_rest_api_and_remote_client(self) -> None:
        lab = Lab(db_path=":memory:", seed_demo=True)
        web_app = DAMFWebApp(lab=lab)
        try:
            # Verify UI HTML route
            ui_status, ui_ctype, ui_bytes = web_app.handle_request("GET", "/lab")
            self.assertEqual(ui_status, 200)
            self.assertIn("text/html", ui_ctype)
            self.assertIn(b"Dynamic Lab Network", ui_bytes)

            client = RemoteLabClient("http://127.0.0.1:8080", app=web_app)
            status = client.status()
            self.assertEqual(status["total_devices"], 5)

            devs = client.list_devices(board_type="ti-am62x")
            self.assertEqual(len(devs), 1)
            target_name = devs[0]["name"]

            res_info = client.reserve(target_name, owner="remote-ci")
            self.assertEqual(res_info["device"]["state"], "reserved")

            cmd_info = client.run_command(target_name, "echo hi")
            self.assertEqual(cmd_info["returncode"], 0)

            rel_info = client.release(target_name)
            self.assertEqual(rel_info["device"]["state"], "available")
        finally:
            lab.close()

    def test_cli_commands_and_legacy_flow(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_file = Path(tmpdir) / "cli.db"
            self.assertEqual(cli_main(["--db", str(db_file), "--seed-demo", "devices", "--json"]), 0)
            self.assertEqual(
                cli_main(["--db", str(db_file), "reserve", "--name", "rpi4-lab-01", "--owner", "me"]),
                0,
            )
            self.assertEqual(cli_main(["--db", str(db_file), "release", "rpi4-lab-01"]), 0)

            # Test legacy DeviceManager + TestRequest flow
            cfg_file = Path(tmpdir) / "cfg.yml"
            job_file = Path(tmpdir) / "job.yml"
            cfg_file.write_text(
                f"workspace:\n  root_path: {tmpdir}/ws_\n  logs_dir: logs\n  git_dir: git\n  test_results_dir: test_results\n  temp_dir: tmp\nglobal_settings:\n  board_files_path: {tmpdir}\n",
                encoding="utf-8",
            )
            job_file.write_text(
                "boards:\n  master: raspberry-pi-4\ninstance_config:\n  master:\n    boot_method: ramdisk\ntests:\n  master:\n    - uname\n",
                encoding="utf-8",
            )
            from DeviceManager import DeviceManager

            dm = DeviceManager.DeviceManager(str(cfg_file), debug=True)
            dm.submit_test_request(safe_load_yaml(job_file.read_text(encoding="utf-8")))
            xml_report = Path(dm.workspace) / "test_results" / "uname.xml"
            self.assertTrue(xml_report.exists())


if __name__ == "__main__":
    unittest.main()
