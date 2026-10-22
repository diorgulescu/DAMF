"""SSH/SCP transport for embedded Linux/Unix boards (Raspberry Pi, BeagleBone, TI Linux, BSD, etc.)."""

from __future__ import annotations

from pathlib import Path
import shlex
import shutil
import socket
import subprocess
import time
from typing import Any

from damf.exceptions import CommandTimeoutError, TransportError
from damf.models import CommandResult, DeviceSpec
from damf.transports.base import Transport


def parse_os_probe_output(raw_output: str, fallback_hint: str = "") -> dict[str, str]:
    """Parse output from a remote OS/init probe into structured OS metadata.

    Returns a dictionary containing:
      - kernel: e.g. 'Linux', 'FreeBSD', 'OpenBSD', 'NetBSD', 'Darwin', 'SunOS'
      - distro: e.g. 'debian', 'raspbian', 'ubuntu', 'poky', 'buildroot', 'busybox', 'alpine', 'freebsd', 'macos'
      - init_system: e.g. 'systemd', 'busybox', 'sysvinit', 'openrc', 'bsdinit', 'launchd'
      - arch: e.g. 'aarch64', 'armv7l', 'x86_64'
      - pretty_name: Human-readable OS description
    """
    sections: dict[str, str] = {}
    current_key = ""
    buf: list[str] = []
    for line in raw_output.splitlines():
        if line.startswith("__DAMF_") and line.endswith("__"):
            if current_key:
                sections[current_key] = "\n".join(buf).strip()
            current_key = line.strip("_")
            buf = []
        else:
            buf.append(line)
    if current_key:
        sections[current_key] = "\n".join(buf).strip()

    kernel = sections.get("DAMF_KERNEL", "").splitlines()[0].strip() if sections.get("DAMF_KERNEL") else ""
    arch = sections.get("DAMF_ARCH", "").splitlines()[0].strip() if sections.get("DAMF_ARCH") else ""
    os_release_text = sections.get("DAMF_OS_RELEASE", "")
    init_comm = sections.get("DAMF_INIT", "").splitlines()[0].strip() if sections.get("DAMF_INIT") else ""
    reboot_target = sections.get("DAMF_REBOOT_BIN", "")

    os_release: dict[str, str] = {}
    for line in os_release_text.splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            os_release[k.strip().upper()] = v.strip().strip('"').strip("'")

    hint_low = (fallback_hint or raw_output).lower()
    if not kernel:
        if "freebsd" in hint_low:
            kernel = "FreeBSD"
        elif "openbsd" in hint_low:
            kernel = "OpenBSD"
        elif "netbsd" in hint_low:
            kernel = "NetBSD"
        elif "darwin" in hint_low or "macos" in hint_low:
            kernel = "Darwin"
        elif "sunos" in hint_low or "solaris" in hint_low:
            kernel = "SunOS"
        else:
            kernel = "Linux"

    distro = os_release.get("ID", "").lower()
    pretty_name = os_release.get("PRETTY_NAME", "")
    if not distro:
        if "raspbian" in hint_low or "raspberry" in hint_low:
            distro = "raspbian"
        elif "debian" in hint_low:
            distro = "debian"
        elif "ubuntu" in hint_low:
            distro = "ubuntu"
        elif "poky" in hint_low or "yocto" in hint_low or "arago" in hint_low or "ti processor sdk" in hint_low:
            distro = "poky"
        elif "buildroot" in hint_low:
            distro = "buildroot"
        elif "busybox" in hint_low:
            distro = "busybox"
        elif "alpine" in hint_low:
            distro = "alpine"
        elif kernel in ("FreeBSD", "OpenBSD", "NetBSD"):
            distro = kernel.lower()
        elif kernel == "Darwin":
            distro = "macos"
        else:
            distro = "linux"

    # Determine init system
    init_low = f"{init_comm} {reboot_target} {hint_low}".lower()
    if "systemd" in init_low or distro in ("raspbian", "debian", "ubuntu"):
        init_system = "systemd"
    elif "busybox" in init_low or distro in ("busybox", "buildroot"):
        init_system = "busybox"
    elif "openrc" in init_low or distro == "alpine":
        init_system = "openrc"
    elif kernel in ("FreeBSD", "OpenBSD", "NetBSD"):
        init_system = "bsdinit"
    elif kernel == "Darwin":
        init_system = "launchd"
    else:
        init_system = "sysvinit"

    if not pretty_name:
        pretty_name = f"{kernel} ({distro}, {init_system})"

    return {
        "kernel": kernel,
        "distro": distro,
        "init_system": init_system,
        "arch": arch or "unknown",
        "pretty_name": pretty_name,
    }


def determine_reboot_command(os_info: dict[str, str], user: str = "root") -> str:
    """Select the appropriate Linux/Unix reboot command based on target OS and user privileges."""
    kernel = os_info.get("kernel", "Linux")
    init_system = os_info.get("init_system", "sysvinit")
    distro = os_info.get("distro", "linux")
    sudo_prefix = "" if user == "root" else "sudo -n "

    if kernel == "Linux":
        if init_system == "systemd":
            return f"{sudo_prefix}systemctl reboot || {sudo_prefix}/sbin/reboot"
        if init_system == "busybox" or distro in ("busybox", "buildroot"):
            return f"{sudo_prefix}/sbin/reboot || {sudo_prefix}reboot -f"
        if init_system == "openrc":
            return f"{sudo_prefix}/sbin/reboot"
        # SysVinit / Yocto / Arago / generic embedded Linux
        return f"{sudo_prefix}/sbin/reboot || {sudo_prefix}shutdown -r now"

    if kernel in ("FreeBSD", "OpenBSD", "NetBSD"):
        return f"{sudo_prefix}/sbin/shutdown -r now || {sudo_prefix}/sbin/reboot"

    if kernel == "Darwin":
        return f"{sudo_prefix}/sbin/shutdown -r now"

    if kernel == "SunOS":
        return f"{sudo_prefix}/usr/sbin/reboot"

    return f"{sudo_prefix}reboot || {sudo_prefix}/sbin/reboot || {sudo_prefix}shutdown -r now"


class SSHTransport(Transport):
    """Communicates with Linux/Unix targets over OpenSSH / Dropbear SSH and SCP."""

    defproperty_defaults = {
        "user": "root",
        "port": 22,
        "strict_host_key_checking": False,
        "connect_timeout": 10,
    }

    @property
    def host(self) -> str:
        return self.spec.ip_address or str(self.config.get("host", ""))

    @property
    def user(self) -> str:
        return str(self.config.get("user", "root"))

    @property
    def port(self) -> int:
        return int(self.config.get("port", 22))

    @property
    def identity_file(self) -> str | None:
        return self.config.get("identity_file") or self.config.get("key_filename")

    @property
    def password(self) -> str | None:
        pwd = self.config.get("password")
        return str(pwd) if pwd else None

    def _ssh_base_args(self, is_scp: bool = False, interactive: bool = False) -> list[str]:
        binary = "scp" if is_scp else "ssh"
        port_flag = "-P" if is_scp else "-p"
        prefix: list[str] = []
        use_batch_mode = not interactive

        if self.password and shutil.which("sshpass"):
            prefix = ["sshpass", "-p", self.password]
            use_batch_mode = False

        args = prefix + [
            binary,
            port_flag,
            str(self.port),
            "-o",
            f"ConnectTimeout={int(self.config.get('connect_timeout', 10))}",
        ]
        if use_batch_mode:
            args.extend(["-o", "BatchMode=yes"])
        if not self.config.get("strict_host_key_checking", False):
            args.extend(["-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null"])
        if self.identity_file:
            args.extend(["-i", str(self.identity_file)])
        return args

    def build_interactive_ssh_command(self) -> list[str]:
        """Return the CLI argv list to open an interactive SSH shell to this device."""
        if not self.host:
            raise TransportError(f"Device '{self.spec.name}' has no IP address configured for SSH")
        return self._ssh_base_args(is_scp=False, interactive=True) + [f"{self.user}@{self.host}"]

    def connect(self, verify_auth: bool = False) -> None:
        """Connect to the target SSH endpoint (and optionally verify shell auth)."""
        if not self.host:
            raise TransportError(f"Device '{self.spec.name}' has no IP address configured for SSH")
        if self.config.get("simulated", False):
            self.connected = True
            self.spec.attributes.setdefault("ssh_banner", "SSH-2.0-Simulated_DAMF")
            return
        timeout = float(self.config.get("connect_timeout", 5))
        try:
            with socket.create_connection((self.host, self.port), timeout=timeout) as sock:
                sock.settimeout(min(timeout, 2.0))
                try:
                    banner = sock.recv(128).decode("utf-8", errors="ignore").strip()
                    if banner:
                        self.spec.attributes["ssh_banner"] = banner
                except OSError:
                    pass
                self.connected = True
        except OSError as exc:
            raise TransportError(f"Cannot reach SSH port {self.host}:{self.port} for '{self.spec.name}': {exc}") from exc

        if verify_auth:
            probe = self.run("echo damf_ssh_ready", timeout=timeout)
            if not probe.ok:
                self.connected = False
                raise TransportError(
                    f"SSH authentication failed for {self.user}@{self.host}:{self.port} "
                    f"on '{self.spec.name}': {probe.stderr.strip()}"
                )

    def disconnect(self) -> None:
        self.connected = False

    def run(
        self,
        command: str,
        timeout: float = 60.0,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
    ) -> CommandResult:
        if not self.host:
            raise TransportError(f"Device '{self.spec.name}' has no IP address for SSH execution")

        remote_cmd = command
        if cwd:
            remote_cmd = f"cd {shlex.quote(cwd)} && {remote_cmd}"
        if env:
            exports = " ".join(f"{k}={shlex.quote(str(v))}" for k, v in env.items())
            remote_cmd = f"export {exports}; {remote_cmd}"

        if self.config.get("simulated", False):
            return CommandResult(
                command=command,
                returncode=0,
                stdout=f"[simulated-ssh:{self.spec.name}] {command}\n",
                stderr="",
                duration_sec=0.01,
                device_name=self.spec.name,
            )

        ssh_cmd = self._ssh_base_args(is_scp=False) + [
            f"{self.user}@{self.host}",
            f"sh -c {shlex.quote(remote_cmd)}",
        ]
        start = time.monotonic()
        try:
            proc = subprocess.run(
                ssh_cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise CommandTimeoutError(
                f"SSH command timed out after {timeout}s on '{self.spec.name}': {command}"
            ) from exc
        except OSError as exc:
            raise TransportError(f"SSH execution failed on '{self.spec.name}': {exc}") from exc

        return CommandResult(
            command=command,
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            duration_sec=round(time.monotonic() - start, 4),
            device_name=self.spec.name,
        )

    def detect_os(self, force_refresh: bool = False) -> dict[str, str]:
        """Probe the remote target over SSH to determine its OS kernel, distro, and init system."""
        if not force_refresh and isinstance(self.spec.attributes.get("os_info"), dict):
            cached = dict(self.spec.attributes["os_info"])
            if "reboot_command" not in cached:
                cached["reboot_command"] = determine_reboot_command(cached, user=self.user)
            return cached

        probe_script = (
            "echo __DAMF_KERNEL__; uname -s 2>/dev/null || true; "
            "echo __DAMF_ARCH__; uname -m 2>/dev/null || true; "
            "echo __DAMF_OS_RELEASE__; cat /etc/os-release 2>/dev/null || true; "
            "echo __DAMF_INIT__; ps -p 1 -o comm= 2>/dev/null || true; "
            "echo __DAMF_REBOOT_BIN__; ls -l /sbin/reboot 2>/dev/null || true"
        )

        hint_parts = [
            str(self.spec.attributes.get("os", "")),
            str(self.config.get("os", "")),
            self.spec.deployed_image,
            self.spec.board_type,
        ]
        fallback_hint = " ".join(p for p in hint_parts if p)

        if self.config.get("simulated", False):
            sim_probe = self.config.get("simulated_os_probe", "")
            os_info = parse_os_probe_output(str(sim_probe), fallback_hint=fallback_hint)
        else:
            res = self.run(probe_script, timeout=10.0)
            if not res.ok and not res.stdout.strip():
                raise TransportError(
                    f"Unable to detect OS over SSH on '{self.spec.name}' ({self.user}@{self.host}): {res.stderr.strip()}"
                )
            os_info = parse_os_probe_output(res.stdout, fallback_hint=fallback_hint)

        os_info["reboot_command"] = determine_reboot_command(os_info, user=self.user)
        self.spec.attributes["os_info"] = os_info
        return os_info

    def reboot_over_ssh(self, timeout: float = 15.0, force_os_probe: bool = False) -> CommandResult:
        """Detect the OS running on the target and execute the appropriate Linux/Unix reboot command over SSH."""
        os_info = self.detect_os(force_refresh=force_os_probe)
        reboot_cmd = os_info["reboot_command"]
        self.spec.attributes["last_reboot_command"] = reboot_cmd

        if self.config.get("simulated", False):
            self.spec.power_state = "on"
            return CommandResult(
                command=reboot_cmd,
                returncode=0,
                stdout=(
                    f"[simulated-ssh:{self.spec.name}] Detected OS: {os_info['pretty_name']} -> "
                    f"Executed: {reboot_cmd}\n"
                ),
                stderr="",
                duration_sec=0.02,
                device_name=self.spec.name,
            )

        res = self.run(reboot_cmd, timeout=timeout)
        # SSH exit code 255 is normal when the remote sshd/dropbear closes the socket during system reboot
        if res.returncode in (0, 255) or "closed by remote host" in res.stderr.lower():
            self.spec.power_state = "on"
            return CommandResult(
                command=reboot_cmd,
                returncode=0,
                stdout=res.stdout or f"Reboot initiated on {self.spec.name} ({os_info['pretty_name']})\n",
                stderr=res.stderr,
                duration_sec=res.duration_sec,
                device_name=self.spec.name,
            )

        raise TransportError(
            f"Reboot command '{reboot_cmd}' failed on '{self.spec.name}' "
            f"(exit {res.returncode}): {res.stderr or res.stdout}"
        )

    def upload(self, local_path: str | Path, remote_path: str) -> None:
        if self.config.get("simulated", False):
            return
        src = Path(local_path)
        if not src.exists():
            raise TransportError(f"Local path does not exist for upload: {src}")
        scp_cmd = self._ssh_base_args(is_scp=True)
        if src.is_dir():
            scp_cmd.append("-r")
        scp_cmd.extend([str(src), f"{self.user}@{self.host}:{remote_path}"])
        proc = subprocess.run(scp_cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            raise TransportError(f"SCP upload to '{self.spec.name}' failed: {proc.stderr}")

    def download(self, remote_path: str, local_path: str | Path) -> None:
        if self.config.get("simulated", False):
            return
        dst = Path(local_path)
        dst.parent.mkdir(parents=True, exist_ok=True)
        scp_cmd = self._ssh_base_args(is_scp=True) + [
            "-r",
            f"{self.user}@{self.host}:{remote_path}",
            str(dst),
        ]
        proc = subprocess.run(scp_cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            raise TransportError(f"SCP download from '{self.spec.name}' failed: {proc.stderr}")
