"""Pluggable power controllers for lab devices (Smart Plugs/Webhooks, USB Hubs, IPMI, Custom CLI, Simulated)."""

from __future__ import annotations

from abc import ABC, abstractmethod
import json
import subprocess
import time
from typing import Any
import urllib.error
import urllib.request

from damf.exceptions import ConfigurationError, PowerControlError
from damf.models import DeviceSpec, PowerType


class PowerController(ABC):
    """Abstract base class for controlling board power state."""

    def __init__(self, spec: DeviceSpec):
        self.spec = spec

    @property
    def config(self) -> dict[str, Any]:
        return self.spec.power_config

    @abstractmethod
    def power_on(self) -> None:
        """Turn power on for the target board."""

    @abstractmethod
    def power_off(self) -> None:
        """Turn power off for the target board."""

    def reboot(self, delay_sec: float = 0.5) -> None:
        """Power cycle the board."""
        self.power_off()
        if delay_sec > 0:
            time.sleep(delay_sec)
        self.power_on()

    @abstractmethod
    def status(self) -> str:
        """Return 'on', 'off', or 'unknown'."""


class SimulatedPowerController(PowerController):
    """In-memory power controller for simulation, local testing, and boards without external PDUs."""

    def power_on(self) -> None:
        self.spec.power_state = "on"

    def power_off(self) -> None:
        self.spec.power_state = "off"

    def status(self) -> str:
        return self.spec.power_state or "off"


class WebhookPowerController(PowerController):
    """Controls smart plugs / network relays (Shelly, Tasmota, Home Assistant, REST PDUs) over HTTP."""

    def _call_url(self, url: str, method: str = "POST", payload: dict[str, Any] | None = None) -> str:
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Content-Type": "application/json"} if payload is not None else {}
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=float(self.config.get("timeout", 10.0))) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, OSError) as exc:
            raise PowerControlError(f"Webhook power call to '{url}' failed for '{self.spec.name}': {exc}") from exc

    def power_on(self) -> None:
        url = self.config.get("on_url")
        if not url:
            raise PowerControlError(f"Missing 'on_url' in power_config for '{self.spec.name}'")
        self._call_url(url, method=str(self.config.get("method", "POST")), payload=self.config.get("on_payload"))
        self.spec.power_state = "on"

    def power_off(self) -> None:
        url = self.config.get("off_url")
        if not url:
            raise PowerControlError(f"Missing 'off_url' in power_config for '{self.spec.name}'")
        self._call_url(url, method=str(self.config.get("method", "POST")), payload=self.config.get("off_payload"))
        self.spec.power_state = "off"

    def status(self) -> str:
        status_url = self.config.get("status_url")
        if not status_url:
            return self.spec.power_state or "unknown"
        body = self._call_url(status_url, method="GET").lower()
        if "on" in body or "true" in body:
            self.spec.power_state = "on"
        elif "off" in body or "false" in body:
            self.spec.power_state = "off"
        return self.spec.power_state


class USBHubPowerController(PowerController):
    """Controls per-port USB VBUS power using `uhubctl` (popular for Raspberry Pi & TI dev boards)."""

    def _run_uhubctl(self, action: str) -> None:
        hub = str(self.config.get("location", ""))
        port = str(self.config.get("port", "1"))
        cmd = ["uhubctl", "-a", action, "-p", port]
        if hub:
            cmd.extend(["-l", hub])
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            raise PowerControlError(f"uhubctl failed for '{self.spec.name}': {proc.stderr or proc.stdout}")

    def power_on(self) -> None:
        self._run_uhubctl("on")
        self.spec.power_state = "on"

    def power_off(self) -> None:
        self._run_uhubctl("off")
        self.spec.power_state = "off"

    def status(self) -> str:
        return self.spec.power_state or "unknown"


class IPMIPowerController(PowerController):
    """Controls server and industrial boards via `ipmitool`."""

    def _ipmi_cmd(self, power_action: str) -> str:
        host = self.config.get("bmc_ip") or self.spec.ip_address
        user = self.config.get("username", "admin")
        password = self.config.get("password", "admin")
        if not host:
            raise PowerControlError(f"Missing 'bmc_ip' in power_config for IPMI device '{self.spec.name}'")
        cmd = [
            "ipmitool",
            "-I",
            "lanplus",
            "-H",
            str(host),
            "-U",
            str(user),
            "-P",
            str(password),
            "chassis",
            "power",
            power_action,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            raise PowerControlError(f"ipmitool {power_action} failed on '{self.spec.name}': {proc.stderr}")
        return proc.stdout.strip()

    def power_on(self) -> None:
        self._ipmi_cmd("on")
        self.spec.power_state = "on"

    def power_off(self) -> None:
        self._ipmi_cmd("off")
        self.spec.power_state = "off"

    def status(self) -> str:
        out = self._ipmi_cmd("status").lower()
        if "is on" in out:
            self.spec.power_state = "on"
        elif "is off" in out:
            self.spec.power_state = "off"
        return self.spec.power_state


class CommandPowerController(PowerController):
    """Executes custom shell commands for lab PDUs (e.g. pdu-client or legacy target commands)."""

    def _exec(self, key: str, default_state: str) -> None:
        template = self.config.get(key)
        if not template:
            raise PowerControlError(f"Missing '{key}' in power_config for '{self.spec.name}'")
        cmd = str(template).format(name=self.spec.name, ip=self.spec.ip_address)
        proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            raise PowerControlError(f"Power command '{cmd}' failed for '{self.spec.name}': {proc.stderr}")
        self.spec.power_state = default_state

    def power_on(self) -> None:
        self._exec("on_cmd", "on")

    def power_off(self) -> None:
        self._exec("off_cmd", "off")

    def status(self) -> str:
        return self.spec.power_state or "unknown"


def create_power_controller(spec: DeviceSpec) -> PowerController:
    """Instantiate the configured PowerController for a DeviceSpec."""
    kind = (spec.power_type or PowerType.SIMULATED.value).lower()
    if kind == PowerType.SIMULATED.value:
        return SimulatedPowerController(spec)
    if kind == PowerType.WEBHOOK.value:
        return WebhookPowerController(spec)
    if kind == PowerType.USB_HUB.value:
        return USBHubPowerController(spec)
    if kind == PowerType.IPMI.value:
        return IPMIPowerController(spec)
    if kind == PowerType.COMMAND.value:
        return CommandPowerController(spec)
    raise ConfigurationError(f"Unsupported power controller type '{spec.power_type}' for '{spec.name}'")
