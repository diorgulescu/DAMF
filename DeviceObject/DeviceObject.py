import logging
import os
from pathlib import Path
import subprocess

from damf.config import safe_load_all_yaml
from damf.device import Device
from damf.models import DeviceSpec


class DeviceObject:
    """Used as a helper for the DeviceManager class, in order to provide a way to easily
    manage board-level operations, like flashing, reflashing, power cycle management and
    other tasks. Wraps the modern `damf.Device` abstraction while keeping legacy methods."""

    def __init__(self, board_id, board_type, board_role, res_id, boardfile_path="", workspace_dir=".", board_info=''):
        self.board_name = board_id
        self.board_type = board_type
        self.board_info = board_info
        self.board_role = board_role
        self.board_ip = "127.0.0.1"
        self.reservation_id = res_id
        self.boardfile_path = boardfile_path
        self.attributes = {}
        self.ramdisk_commands = []
        self.nfs_commands = []
        self.workspace = workspace_dir

        # Board attributes
        self.has_ssh = True
        self.ipmi_managed = False
        self.ipmi_tools = {}
        self.root_prompt = "#"

        # Hardware attributes
        self.arch = "arm64"
        self.nb_of_eth_ports = "1"
        self.bootloader = "u-boot"
        self.ivlab_id = ""
        self.cpu = ""

        self.has_test_results = False

        # We create our logger, including a formatter
        self.logger = logging.getLogger(f"{__name__}.{board_id}")
        self.logger.setLevel(logging.DEBUG)
        log_dir = os.path.join(self.workspace, "logs")
        os.makedirs(log_dir, exist_ok=True)
        if not self.logger.handlers:
            logfile_handler = logging.FileHandler(os.path.join(log_dir, f"{board_id}.log"))
            formatter = logging.Formatter('%(asctime)s[%(levelname)s] %(message)s', datefmt='[%m/%d/%Y][%H:%M:%S]')
            logfile_handler.setFormatter(formatter)
            self.logger.addHandler(logfile_handler)

        self.logger.debug("Created DeviceObject for %s", self.board_name)

        # Perform initial object setup if a board file exists
        self.read_device_file(self.board_type)

        self._spec = DeviceSpec(
            name=self.board_name,
            board_type=self.board_type,
            arch=self.arch,
            ip_address=self.board_ip,
            transport="ssh",
            transport_config={"simulated": True},
            power_type="simulated",
            reservation_id=str(self.reservation_id),
            boot_commands={
                "ramdisk_boot": list(self.ramdisk_commands),
                "nfs_boot": list(self.nfs_commands),
            },
        )
        self.device = Device(self._spec)

    # ATTRIBUTE SETTERS AND GETTERS
    def get_board_name(self):
        """Returns the board name as set for the current object instance"""
        return self.board_name

    def set_board_name(self, new_board_name):
        """Use this to change the board name for this object instance"""
        self.board_name = new_board_name
        self._spec.name = new_board_name

    def get_board_ip(self):
        """Returns the IP address of the board, once booted"""
        return self.board_ip

    def get_board_type(self):
        """Returns the board type"""
        return self.board_type

    def get_board_role(self):
        """Returns the board role (master or slave)"""
        return self.board_role

    def get_board_info(self):
        """Return board info"""
        return self.board_info

    def set_board_info(self, new_board_info):
        self.board_info = new_board_info

    def get_bootloader(self):
        """Returns the bootloader used by the board"""
        return self.bootloader

    def get_reservation_id(self):
        return self.reservation_id

    def set_bootloader(self, new_bootloader):
        self.bootloader = new_bootloader
        self._spec.bootloader = new_bootloader

    # METHODS
    def reset(self):
        """Used to call a reset on the board represented by the current object instance"""
        self.device.reboot()
        return self.device.power_state

    def power_off(self):
        """Power off the board"""
        self.logger.info("Powering off...")
        self.device.power_off()

    def power_on(self):
        """Bring the board power up"""
        self.logger.info("Powering on...")
        self.device.power_on()
        self.logger.info("Board successfully powered on")

    def submit_config_params(self, params_dict):
        """Receive instance configuration details in the form of a dictionary and applies
        the data to the configuration of the current object"""
        for config_section, settings in params_dict.items():
            if not isinstance(settings, dict):
                continue
            if config_section == "ramdisk":
                self.ramdisk_commands = [cmd.replace('{IMAGE}', settings.get("kernel", "")) for cmd in self.ramdisk_commands]
                self.ramdisk_commands = [cmd.replace('{DTB}', settings.get("dtb", "")) for cmd in self.ramdisk_commands]
                self.ramdisk_commands = [cmd.replace('{ROOT_FS}', settings.get("rootfs", "")) for cmd in self.ramdisk_commands]

            if config_section == "nfs":
                self.nfs_commands = [cmd.replace('{IMAGE}', settings.get("kernel", "")) for cmd in self.nfs_commands]
                self.nfs_commands = [cmd.replace('{DTB}', settings.get("dtb", "")) for cmd in self.nfs_commands]
                self.nfs_commands = [cmd.replace('{ROOT_FS}', settings.get("rootfs", "")) for cmd in self.nfs_commands]

        self._spec.boot_commands["ramdisk_boot"] = list(self.ramdisk_commands)
        self._spec.boot_commands["nfs_boot"] = list(self.nfs_commands)

    def read_device_file(self, board_type):
        """Used for loading and reading the contents of the board's device file, which
        contains info such as boot parameters, addresses and specific commands."""
        if not self.boardfile_path:
            return
        candidate = os.path.join(self.boardfile_path, f"{board_type}.yml")
        if not os.path.exists(candidate):
            return
        self.logger.debug("Parsing board file for %s", board_type)
        with open(candidate, "r", encoding="utf-8") as file_stream:
            board_file = safe_load_all_yaml(file_stream)

        for entry in board_file:
            if not isinstance(entry, dict):
                continue
            for section, section_contents in entry.items():
                if section == "commands" and isinstance(section_contents, dict):
                    for command_type, commands in section_contents.items():
                        if command_type == "ramdisk_boot" and isinstance(commands, list):
                            self.ramdisk_commands.extend(commands)
                        if command_type == "nfs_boot" and isinstance(commands, list):
                            self.nfs_commands.extend(commands)

                if section == "attributes" and isinstance(section_contents, dict):
                    for setting, value in section_contents.items():
                        if setting == "root_prompt":
                            self.root_prompt = value
                        if setting == "has_ssh" and str(value).lower() in ("yes", "true"):
                            self.has_ssh = True
                        if setting == "ipmi_managed" and str(value).lower() in ("yes", "true"):
                            self.ipmi_managed = True

                if section == "commands" and self.ipmi_managed and isinstance(section_contents, dict):
                    for ipmi_block, settings in section_contents.items():
                        if ipmi_block == "ipmi_managed" and isinstance(settings, dict):
                            self.ipmi_tools.update(settings)

    def boot_board(self, boot_method):
        """Boot the board using the configured boot method."""
        self.logger.info("Booting board (%s)...", boot_method)
        if self.ipmi_managed and "setup_script" in self.ipmi_tools:
            subprocess.getoutput(self.ipmi_tools["setup_script"])
            return self.device
        return self.device.boot_bootloader(boot_method=boot_method)

    def run_tests(self, test_request_obj):
        """Used for invoking the available tests. Receives the test request object and, based
        on the contents, passes the suitable directives"""
        results_dir = Path(self.workspace) / "test_results"
        results_dir.mkdir(parents=True, exist_ok=True)
        for test in test_request_obj.master_tests:
            self.logger.info("Running test %s...", test)
            res = self.device.run(test)
            status = "PASS" if res.ok else "FAIL"
            result_file = results_dir / f"{Path(test).name}_test_result"
            result_file.write_text(f"{test}: {status}\n", encoding="utf-8")
        self.has_test_results = True
        return True
