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
    DAMFAgent,
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
    collect_telemetry,
    create_http_server,
    determine_reboot_command,
    dump_yaml,
    generate_posix_shell_agent,
    lookup_mac_vendor,
    normalize_mac,
    parse_os_probe_output,
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
        try:
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
        finally:
            lab.close()

    def test_cluster_acquisition_and_ttl_expiry(self) -> None:
        lab = Lab(db_path=":memory:", seed_demo=True)
        try:
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
        finally:
            lab.close()

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
            dm.resource_pool.close()


class TestTopologySSHAndContextReboot(unittest.TestCase):
    """Tests for manual topology definition, SSH connection, and OS-aware SSH reboot."""

    def test_manual_topology_device_creation_and_bidirectional_links(self) -> None:
        lab = Lab(db_path=":memory:", seed_demo=False)
        try:
            rpi = lab.define_device(
                name="rpi4-custom-01",
                board_type="raspberry-pi-4",
                ip_address="192.168.50.10",
                ssh_user="pi",
                ssh_port=2222,
                identity_file="/home/pi/.ssh/id_ed25519",
                os_hint="raspbian",
                simulated=True,
            )
            self.assertEqual(rpi.subnet, "192.168.50.0/24")
            self.assertEqual(rpi.transport_config["user"], "pi")
            self.assertEqual(rpi.transport_config["port"], 2222)

            ti = lab.define_device(
                name="ti-evm-custom-01",
                board_type="ti-am62x",
                ip_address="192.168.50.20",
                ssh_user="root",
                os_hint="busybox",
                connected_to=["rpi4-custom-01"],
                simulated=True,
            )
            self.assertIn("rpi4-custom-01", ti.connected_to)
            # Verify bidirectional link sync on rpi4-custom-01
            rpi_reloaded = lab.pool.get_device("rpi4-custom-01")
            assert rpi_reloaded is not None
            self.assertIn("ti-evm-custom-01", rpi_reloaded.connected_to)

            topo = lab.topology()
            self.assertIn("192.168.50.0/24", topo["subnets"])
            self.assertEqual(len(topo["links"]), 1)

            # Unlink and re-link
            lab.unlink_devices("rpi4-custom-01", "ti-evm-custom-01")
            self.assertEqual(len(lab.topology()["links"]), 0)
            lab.link_devices("rpi4-custom-01", "ti-evm-custom-01")
            self.assertEqual(len(lab.topology()["links"]), 1)
        finally:
            lab.close()

    def test_ssh_connection_and_os_context_aware_reboot(self) -> None:
        # 1. Verify probe parsing & reboot command selection across OS contexts
        debian_probe = (
            "__DAMF_KERNEL__\nLinux\n__DAMF_ARCH__\naarch64\n"
            "__DAMF_OS_RELEASE__\nID=debian\nPRETTY_NAME=\"Debian GNU/Linux 12 (bookworm)\"\n"
            "__DAMF_INIT__\nsystemd\n"
        )
        os_deb = parse_os_probe_output(debian_probe)
        self.assertEqual(os_deb["kernel"], "Linux")
        self.assertEqual(os_deb["distro"], "debian")
        self.assertEqual(os_deb["init_system"], "systemd")
        self.assertEqual(
            determine_reboot_command(os_deb, user="pi"),
            "sudo -n systemctl reboot || sudo -n /sbin/reboot",
        )
        self.assertEqual(
            determine_reboot_command(os_deb, user="root"),
            "systemctl reboot || /sbin/reboot",
        )

        busybox_probe = (
            "__DAMF_KERNEL__\nLinux\n__DAMF_ARCH__\narmv7l\n"
            "__DAMF_OS_RELEASE__\nID=buildroot\nPRETTY_NAME=\"Buildroot 2026.02\"\n"
            "__DAMF_INIT__\ninit\n__DAMF_REBOOT_BIN__\nlrwxrwxrwx 1 root root 14 /sbin/reboot -> ../bin/busybox\n"
        )
        os_bb = parse_os_probe_output(busybox_probe)
        self.assertEqual(os_bb["init_system"], "busybox")
        self.assertEqual(
            determine_reboot_command(os_bb, user="root"),
            "/sbin/reboot || reboot -f",
        )

        freebsd_probe = "__DAMF_KERNEL__\nFreeBSD\n__DAMF_ARCH__\narm64\n__DAMF_INIT__\ninit\n"
        os_bsd = parse_os_probe_output(freebsd_probe)
        self.assertEqual(os_bsd["kernel"], "FreeBSD")
        self.assertEqual(
            determine_reboot_command(os_bsd, user="admin"),
            "sudo -n /sbin/shutdown -r now || sudo -n /sbin/reboot",
        )

        # 2. Verify end-to-end SSH connect & reboot via Lab, REST API, and CLI
        lab = Lab(db_path=":memory:", seed_demo=True)
        web_app = DAMFWebApp(lab=lab)
        client = RemoteLabClient(app=web_app)
        try:
            created = client.add_device(
                name="beagleplay-ssh-01",
                board_type="ti-am62x",
                ip_address="192.168.10.188",
                ssh_user="debian",
                ssh_port=22,
                os_hint="debian",
                connected_to=["rpi4-lab-01"],
                simulated=True,
            )
            self.assertEqual(created["name"], "beagleplay-ssh-01")

            conn_info = client.connect_ssh("beagleplay-ssh-01")
            self.assertTrue(conn_info["connected"])
            self.assertEqual(conn_info["os_info"]["init_system"], "systemd")
            self.assertIn("ssh", conn_info["interactive_cmd"])

            reb_info = client.reboot("beagleplay-ssh-01", via_ssh=True)
            self.assertEqual(reb_info["returncode"], 0)
            self.assertEqual(
                reb_info["reboot_command"],
                "sudo -n systemctl reboot || sudo -n /sbin/reboot",
            )
        finally:
            lab.close()

        # 3. Verify CLI `add-device`, `link`, `ssh`, and `reboot`
        with tempfile.TemporaryDirectory() as tmpdir:
            db_file = Path(tmpdir) / "topo.db"
            self.assertEqual(
                cli_main(
                    [
                        "--db",
                        str(db_file),
                        "add-device",
                        "ti-busybox-board",
                        "--ip",
                        "192.168.10.77",
                        "--type",
                        "ti-am335x",
                        "--user",
                        "root",
                        "--os",
                        "busybox",
                        "--simulated",
                    ]
                ),
                0,
            )
            self.assertEqual(cli_main(["--db", str(db_file), "ssh", "ti-busybox-board"]), 0)
            self.assertEqual(cli_main(["--db", str(db_file), "reboot", "ti-busybox-board"]), 0)


class TestTargetHeartbeatAgentAndTelemetry(unittest.TestCase):
    """Tests for the two-tier target heartbeat agent, SSH deployment, telemetry, and offline detection."""

    def test_agent_telemetry_collection_and_posix_shell_generator(self) -> None:
        snap = collect_telemetry(device_name="rpi4-test", board_type="raspberry-pi-4", log_lines=5)
        self.assertEqual(snap["device_name"], "rpi4-test")
        self.assertIn("load_1m", snap)
        self.assertIn("mem_percent", snap)
        self.assertIsInstance(snap["logs"], list)

        sh_script = generate_posix_shell_agent("http://192.168.10.1:8080", "ti-am335x-01", interval=10)
        self.assertIn("#!/bin/sh", sh_script)
        self.assertIn("/api/v1/agent/heartbeat", sh_script)
        self.assertIn("ti-am335x-01", sh_script)

    def test_agent_push_heartbeat_deploy_and_offline_timeout(self) -> None:
        lab = Lab(db_path=":memory:", seed_demo=True)
        web_app = DAMFWebApp(lab=lab)
        client = RemoteLabClient(app=web_app)
        try:
            # 1. Push a heartbeat from DAMFAgent to the server
            agent = DAMFAgent(device_name="rpi4-lab-01", app=web_app)
            ack = agent.send_heartbeat(
                {
                    "device_name": "rpi4-lab-01",
                    "load_1m": 1.42,
                    "load_5m": 0.88,
                    "load_15m": 0.45,
                    "mem_total_mb": 4096.0,
                    "mem_used_mb": 1024.0,
                    "mem_percent": 25.0,
                    "cpu_temp_c": 51.2,
                    "uptime_seconds": 3600.0,
                    "logs": ["[120.1] kernel: eth0 link becomes ready", "[125.0] systemd: target reached"],
                }
            )
            self.assertTrue(ack["ack"])

            # 2. Fetch vital telemetry via REST client
            tel = client.get_telemetry("rpi4-lab-01")
            self.assertEqual(tel["load_1m"], 1.42)
            self.assertEqual(tel["cpu_temp_c"], 51.2)
            self.assertEqual(len(tel["logs"]), 2)

            # 3. Deploy Tier-1 (Python) agent on Debian board & Tier-2 (POSIX sh) agent on BusyBox board
            dep_py = client.deploy_agent("rpi4-lab-01", server_url="http://192.168.10.1:8080", interval=15)
            self.assertEqual(dep_py["agent_tier"], "python")

            lab.define_device(
                name="ti-minimal-busybox",
                board_type="ti-am335x",
                ip_address="192.168.10.199",
                os_hint="busybox",
                simulated=True,
            )
            dep_sh = client.deploy_agent("ti-minimal-busybox", server_url="http://192.168.10.1:8080", interval=15)
            self.assertEqual(dep_sh["agent_tier"], "posix-sh")

            # 4. Simulate missed heartbeats -> mark offline -> recover on next heartbeat
            spec = lab.pool.get_device("ti-minimal-busybox")
            assert spec is not None
            spec.last_seen = time.time() - 120.0
            lab.pool.register_device(spec, overwrite=True)

            offline_list = lab.check_agent_health(timeout_seconds=45.0)
            self.assertIn("ti-minimal-busybox", offline_list)
            self.assertEqual(lab.pool.get_device("ti-minimal-busybox").state, "offline")  # type: ignore[union-attr]

            # Next heartbeat brings it right back to 'available'
            DAMFAgent(device_name="ti-minimal-busybox", app=web_app).send_heartbeat()
            self.assertEqual(lab.pool.get_device("ti-minimal-busybox").state, "available")  # type: ignore[union-attr]
        finally:
            lab.close()


if __name__ == "__main__":
    unittest.main()
