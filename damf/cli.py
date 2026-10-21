"""Command-line interface (`damf`) for discovering, managing, and testing lab devices."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence

from damf.config import load_config_file
from damf.lab import Lab
from damf.web import create_http_server


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="damf",
        description="DAMF — Device Automation and Management Framework CLI",
    )
    parser.add_argument(
        "--db",
        default=str(Path.home() / ".damf" / "damf.db"),
        help="Path to SQLite database (default: ~/.damf/damf.db, or :memory:)",
    )
    parser.add_argument(
        "--seed-demo",
        action="store_true",
        help="Seed demo devices (Raspberry Pi, TI Sitara, BeagleBone, Android) if pool is empty",
    )

    sub = parser.add_subparsers(dest="subcommand")

    # damf devices
    p_dev = sub.add_parser("devices", help="List registered lab devices")
    p_dev.add_argument("--type", dest="board_type", help="Filter by board_type")
    p_dev.add_argument("--state", help="Filter by state (available, reserved, offline)")
    p_dev.add_argument("--json", action="store_true", help="Output JSON")

    # damf discover
    p_disc = sub.add_parser("discover", help="Scan network (ARP/mDNS/Subnet), Serial, and ADB for boards")
    p_disc.add_argument("--subnet", help="Optional subnet CIDR to probe (e.g. 192.168.1.0/24)")
    p_disc.add_argument("--mdns", action="store_true", help="Include mDNS (.local) hostname scan")
    p_disc.add_argument("--all-arp", action="store_true", help="Include non-embedded MAC OUIs from ARP")

    # damf reserve
    p_res = sub.add_parser("reserve", help="Reserve a device from the pool")
    p_res.add_argument("--name", help="Specific device name")
    p_res.add_argument("--type", dest="board_type", help="Board type to reserve")
    p_res.add_argument("--owner", default="cli-user", help="Owner username")
    p_res.add_argument("--ttl", type=float, default=1800.0, help="Reservation TTL in seconds")

    # damf release
    p_rel = sub.add_parser("release", help="Release a reserved device")
    p_rel.add_argument("name", help="Device name to release")

    # damf exec
    p_exec = sub.add_parser("exec", help="Execute a command on a device")
    p_exec.add_argument("name", help="Target device name")
    p_exec.add_argument("command", help="Command string to run")

    # damf run-job
    p_job = sub.add_parser("run-job", help="Run a YAML/JSON test request file")
    p_job.add_argument("job_file", help="Path to YAML or JSON test job definition")
    p_job.add_argument("--output-dir", default="./test_results", help="Directory for JUnit XML output")

    # damf serve
    p_serve = sub.add_parser("serve", help="Start the DAMF Web UI & REST API server")
    p_serve.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    p_serve.add_argument("--port", type=int, default=8080, help="Bind port (default: 8080)")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.db != ":memory:":
        Path(args.db).parent.mkdir(parents=True, exist_ok=True)

    lab = Lab(db_path=args.db, seed_demo=args.seed_demo)
    try:
        return _dispatch_cli(parser, args, lab)
    finally:
        lab.close()


def _dispatch_cli(parser: argparse.ArgumentParser, args: argparse.Namespace, lab: Lab) -> int:

    if args.subcommand == "devices":
        devs = lab.devices(board_type=args.board_type, state=args.state)
        if args.json:
            print(json.dumps([d.to_dict() for d in devs], indent=2))
        else:
            if not devs:
                print("No devices registered in pool. Run `damf --seed-demo devices` or `damf discover`.")
                return 0
            print(f"{'NAME':<24} {'TYPE':<18} {'ARCH':<8} {'IP':<16} {'TRANSPORT':<10} {'STATE':<10} {'OWNER'}")
            print("-" * 98)
            for d in devs:
                print(
                    f"{d.name:<24} {d.board_type:<18} {d.arch:<8} "
                    f"{(d.ip_address or '-'):<16} {d.transport:<10} {d.state:<10} {d.owner or '-'}"
                )
        return 0

    if args.subcommand == "discover":
        found = lab.scan_and_register(
            subnet_cidr=args.subnet,
            include_mdns=args.mdns,
            only_known_arp_vendors=not args.all_arp,
        )
        print(f"Discovered {len(found)} device(s):")
        for d in found:
            print(f"  - {d.name} ({d.board_type}, ip={d.ip_address or 'local'}, transport={d.transport})")
        return 0

    if args.subcommand == "reserve":
        spec, res = lab.pool.reserve(
            name=args.name,
            board_type=args.board_type,
            owner=args.owner,
            ttl_seconds=args.ttl,
        )
        print(f"Reserved '{spec.name}' (reservation_id={res.reservation_id}, owner={res.owner})")
        return 0

    if args.subcommand == "release":
        lab.pool.release(args.name, force=True)
        print(f"Released '{args.name}'")
        return 0

    if args.subcommand == "exec":
        dev = lab.get_device(args.name)
        res = dev.run(args.command)
        if res.stdout:
            sys.stdout.write(res.stdout)
        if res.stderr:
            sys.stderr.write(res.stderr)
        return res.returncode

    if args.subcommand == "run-job":
        job_data = load_config_file(args.job_file)
        board_type = job_data.get("boards", {}).get("master") or job_data.get("board_type")
        dev_name = job_data.get("device_name")
        tests = job_data.get("tests", {}).get("master") or job_data.get("commands") or ["uname -a"]
        suite_name = job_data.get("suite_name", Path(args.job_file).stem)
        with lab.acquire(name=dev_name, board_type=board_type, owner="cli-job") as dev:
            dev.power_on()
            suite = lab.run_test_suite(dev, commands=tests, suite_name=suite_name, output_dir=args.output_dir)
            print(
                f"Job '{suite.suite_name}' on '{dev.name}': "
                f"{suite.passed} passed, {suite.failed} failed, {suite.skipped} skipped"
            )
            return 0 if suite.failed == 0 else 1

    if args.subcommand == "serve":
        if not lab.devices():
            lab.pool.seed_demo_devices()
        server = create_http_server(host=args.host, port=args.port, lab=lab)
        print(f"DAMF Web UI & REST API listening on http://{args.host}:{args.port}")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down DAMF server...")
            server.server_close()
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
