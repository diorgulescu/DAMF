import logging
import os
import subprocess
import time

from Constants import Constants
from DeviceObject import DeviceObject
from ResourcePool import ResourcePool
from ResultParser import ResultParser
from damf.config import safe_load_yaml


class DeviceManager:
    """Provides methods and features for easily managing boards. 
    Available operations are: image loading, bootloader interaction, board reservation 
    management, board communication and output parsing."""

    def __init__(self, cfg_file, debug=False):
        """The DeviceManager constructor, used for declaring, setting and instantiating all
        the attributes & objects that are going to be used throughout the test flow."""
        self.constants = Constants.Constants()
        self.debug_logging = debug

        with open(cfg_file, 'r', encoding='utf-8') as fh:
            config_file_data = safe_load_yaml(fh) or {}

        workspace_cfg = config_file_data.get("workspace", {})
        root_path = workspace_cfg.get("root_path", "./workspace_")
        self.workspace = "{0}{1}/".format(root_path, time.strftime("%Y_%m_%d_%H_%M"))
        self.logs_dir = workspace_cfg.get("logs_dir", "logs")
        self.git_dir = workspace_cfg.get("git_dir", "git")
        self.test_results_dir = workspace_cfg.get("test_results_dir", "test_results")
        self.temp_dir = workspace_cfg.get("temp_dir", "tmp")
        self.workspace_folders = [self.logs_dir, self.git_dir, self.test_results_dir, self.temp_dir]

        self.logfile = '{0}/{1}/damf-main.log'.format(os.path.abspath(self.workspace), self.logs_dir)
        self.board_file_path = config_file_data.get("global_settings", {}).get("board_files_path", "")

        for folder in self.workspace_folders:
            folder_path = os.path.join(self.workspace, folder)
            if not os.path.exists(folder_path):
                os.makedirs(folder_path)

        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.DEBUG if self.debug_logging else logging.INFO)

        if not self.logger.handlers:
            logfile_handler = logging.FileHandler(self.logfile)
            formatter = logging.Formatter('%(asctime)s[%(levelname)s] %(message)s', datefmt='[%m/%d/%Y][%H:%M:%S]')
            logfile_handler.setFormatter(formatter)
            self.logger.addHandler(logfile_handler)

        self.logger.info("DeviceManager and its dependencies are up and running.")
        self.resource_pool = ResourcePool.ResourcePool(self.board_file_path, self.logger)
        self.result_parser = ResultParser.ResultParser(
            os.path.join(self.workspace, self.test_results_dir),
            os.path.join(self.workspace, self.test_results_dir),
        )

    def get_board_types(self):
        """Returns a list of available board types"""
        return self.resource_pool.board_types

    def submit_test_request(self, request_data):
        """Receives request data in YAML/dict format and processes the request."""
        self.logger.info("Test request submitted")
        new_test_request = TestRequest(request_data)
        self.process_request(new_test_request)

    def process_request(self, test_request_object):
        """Begin actions based on the request data."""
        self.logger.debug("master board type: %s", test_request_object.master_board)
        board_name = self.resource_pool.get_board_by_type(test_request_object.master_board)
        board_obj = self.control_board(board_name, test_request_object.master_board, "master")
        try:
            self.perform_board_work(board_obj, test_request_object)
        finally:
            self.unreserve_board(board_name, board_obj.get_reservation_id())

    def perform_board_work(self, board_object, test_request_object):
        board_object.power_on()
        if board_object.get_board_role() in test_request_object.nodes:
            board_object.submit_config_params(test_request_object.nodes[board_object.get_board_role()])
        board_object.boot_board(test_request_object.master_boot_method)

        if len(test_request_object.master_tests) > 0:
            self.logger.debug("Tests found for the master role: %s", test_request_object.master_tests)

        board_object.run_tests(test_request_object)

        if board_object.has_test_results:
            self.logger.info("Test results found. Processing...")
            self.process_test_results2()

    def reserve_board(self, board_name, attempts=3):
        """Perform the necessary operations for reserving the specified board."""
        self.logger.info(self.constants.INFO.get("reservationattempt", "Reserving %s") % board_name)
        _, reservation = self.resource_pool.reserve(name=board_name, owner="device-manager")
        return reservation.reservation_id

    def unreserve_board(self, board, reservation_id):
        """Erase the specified target reservation ID"""
        self.resource_pool.release(board, reservation_id=reservation_id, force=True)

    def control_board(self, board_name, board_type, board_role):
        """Get an instance of the DeviceObject type for board operations."""
        self.logger.info("Attempting to reserve %s...", board_name)
        reservation_id = self.reserve_board(board_name)

        self.logger.info("Creating a new board object...")
        new_board_object = DeviceObject.DeviceObject(
            board_name,
            board_type,
            board_role,
            reservation_id,
            self.resource_pool.board_file_path,
            self.workspace,
        )
        return new_board_object

    def run_command(self, command_string):
        """Runs a command on the current machine/terminal"""
        self.logger.debug("Sending command %s", command_string)
        return subprocess.check_output(command_string, shell=True, text=True)

    def process_test_results(self, board_name):
        self.logger.debug("Calling the ResultParser component...")
        return self.result_parser.process_test_results()

    def process_test_results2(self):
        """The main method dealing with result files parsing."""
        return self.result_parser.process_test_results()

    def write_xml_file(self, test_results, test_suite_name):
        """Used to export the test results gathered during the test run, in JUnit XML format"""
        return self.result_parser.write_junit_xml(test_results, test_suite_name)


class TestRequest:
    """An object used for building request objects based on the info received from the run-damf script."""

    def __init__(self, job_data):
        """Object constructor. We set test request attributes based on the data"""
        self.job_type = ""
        self.job_data = job_data
        self.nodes = {}
        self.slave_boards = []
        self.master_board = ""
        self.env_vars = ""
        self.git_repos = []
        self.repos_list = []
        self.repos_url = ""
        self.master_tests = []
        self.pkg_installer = ""
        self.master_boot_method = "ramdisk"
        self.ipmi_toolkit = {}

        self.determine_test_type()
        self.extract_node_configuration()
        self.get_master_boot_method()
        self.extract_test_info()

    def determine_test_type(self):
        """Determine whether or not this is a multinode scenario"""
        for board_role, board_type in self.job_data.get("boards", {}).items():
            if board_role == "master":
                self.master_board = board_type
            if board_role == "slave":
                self.slave_boards.append(board_type)

        if self.master_board != "" and len(self.slave_boards) == 0:
            self.job_type = "single-node"
        else:
            self.job_type = "multinode"

    def extract_node_configuration(self):
        """Extract information regarding the implied nodes"""
        for board_role, board_instance_config in self.job_data.get("instance_config", {}).items():
            self.nodes.update({board_role: board_instance_config})

    def get_master_boot_method(self):
        """Determine the boot method to be used for the master board"""
        self.master_boot_method = (
            self.job_data.get("instance_config", {}).get("master", {}).get("boot_method", "ramdisk")
        )

    def extract_test_info(self):
        """Used for extracting info about the tests that will be run, along with others related
        to the test run: Git repositories, specific environment variables, etc."""
        for section, section_contents in self.job_data.get("tests", {}).items():
            if section == "toolkit" and isinstance(section_contents, dict):
                if "git_repos" in section_contents:
                    self.git_repos.append(section_contents["git_repos"])
                if "env_vars" in section_contents:
                    env_v = section_contents["env_vars"]
                    self.env_vars = '\n'.join(env_v) if isinstance(env_v, list) else str(env_v)
                self.pkg_installer = section_contents.get("package_installer", "")
                self.repos_url = section_contents.get("package_repository_url", "")
                repos = section_contents.get("repository_list", "")
                self.repos_list = repos.split(' ') if isinstance(repos, str) and repos else []

            if section == "master" and isinstance(section_contents, list):
                for test_name in section_contents:
                    self.master_tests.append(test_name)
