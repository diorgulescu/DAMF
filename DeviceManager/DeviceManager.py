import os
import codecs
import yaml
import time
import sys
# Use pexpect to send local & remote shell commands
import pexpect
import datetime
import logging
import re
import subprocess
import shlex
#import urllib.request
import base64
import queue
from git import Repo
from threading import Thread
from ResourcePool import ResourcePool
from Constants import Constants
from BoardObject import BoardObject
from ResultParser import ResultParser

class DeviceManager:
    """Provides methods and features for easily managing boards. 
    Available operations are: image loading, bootloader interaction, board reservation 
    management, board communication and output parsing."""

    # Instantiate the Constants object and a logger during the 
    # BoardManager construction phase.
    def __init__(self, cfg_file, debug=False):
        """The BoardManager constructor, used for declaring, setting and instantiating all
        the attributes & objects that are going to be used throughout the test flow."""
        # Instantiate the Constants class
        self.constants = Constants.Constants()

        self.debug_logging = debug
        # We need to use queues in order to process the jobs submitted to the framework
        #self.request_queue = queue(maxsize=10)

        # A dictionary used to store the boards available for our tests (we parse additional
        # IVLab attributes in order to extract this)
        #self.available_boards = {}

        # A vector to hold the board types we can work with
        #self.board_types = []

        # BMTF CONFIG LOADING
        # =================================
        # Load the config
        config_file_data = yaml.load(open(cfg_file, 'r'))

        # Create workspace folder structure
        self.workspace = "{0}{1}/".format(config_file_data["workspace"]["root_path"],time.strftime("%Y_%m_%d_%H_%M"))
        self.logs_dir = config_file_data["workspace"]["logs_dir"]
        self.git_dir = config_file_data["workspace"]["git_dir"]
        self.test_results_dir = config_file_data["workspace"]["test_results_dir"]
        self.temp_dir = config_file_data["workspace"]["temp_dir"]
        self.workspace_folders = [self.logs_dir, self.git_dir, self.test_results_dir, self.temp_dir]
        # =================================
        # The absolute path pointing to the workspace
      #  self.workspace = "%s%s/" % (work_dir,time.strftime("%Y_%m_%d_%H_%M"))

        # Specify the log file path
        self.logfile = '{0}/{1}/bmtf-main.log'.format(os.path.abspath(self.workspace), self.logs_dir)

        self.board_file_path = config_file_data["global_settings"]["board_files_path"] 

        # Create the workspace folder structure
       # self.workspace_folders = ["logs", "test_results", "git", "tmp"]
        for folder in self.workspace_folders:
            if not os.path.exists(self.workspace + folder):
                os.makedirs(self.workspace + folder)

        # We create our logger, including a formatter
        self.logger = logging.getLogger(__name__)

        # If desired, enable debug logging
        if self.debug_logging:
            self.logger.setLevel(logging.DEBUG)
        else:
            self.logger.setLevel(logging.INFO)

        logfile_handler = logging.FileHandler(self.logfile)
        formatter = logging.Formatter('%(asctime)s[%(levelname)s] %(message)s',datefmt='[%m/%d/%Y][%H:%M:%S]')
        logfile_handler.setFormatter(formatter)
        self.logger.addHandler(logfile_handler)

        # Send a couple of debug messages
        self.logger.debug("Successfully instantiated %s at %s" % (__name__, hex(id(self))))
        self.logger.debug("Successfully instantiated Constants at %s" % hex(id(self.constants)))
        self.logger.info("BoardManager and its dependencies are up and running.")

        print("BMTF started successfully. Processing your request...")
        # Instantiate the ResourcePool class. The object will already have a list of available
        # boards.
        self.resource_pool = ResourcePool.ResourcePool(self.board_file_path, self.logger)

        # Instantiate the ResultParser component
        #self.result_parser = ResultParser(self.workspace + self.test_results_dir, self.workspace + self.test_results_dir)

    def get_board_types(self):
        """Returns a list of available board types"""
        return self.resource_pool.board_types

    def submit_test_request(self, request_data):
        """Receives request data in YAML format, forwarded by the bmtf-run script (for now).
        Forwards it to process_request() in a distinct thread"""

        # When queues are used, assign IDs to the test requests
        self.logger.info("Test request submitted")
        self.logger.debug("Raw test request data follows:\n %s \n >>> End of raw data" % request_data)
        
        new_test_request = TestRequest(request_data)
        self.process_request(new_test_request)

        #new_test_request = TestRequest(request_data)
        #worker_thread = Thread(target=self.process_request, args=(new_test_request,))
        #worker_thread.setDaemon(True)
        #worker_thread.start()

    def process_request(self, test_request_object):
        """Begin actions based on the request data. Basically, this is where we initiate the 
        whole flow. For now, we only support single-node flows!"""
        # TODO: implement calls to the rest of the objects
        # TODO: implement multinode support

        self.logger.debug("master board type: %s" % test_request_object.master_board)
        # NOTE: For the moment, we only treat single node scenarios
        # First, see if we need to clone any Git repositories
        if len(test_request_object.git_repos) > 0:
            self.logger.debug("Git repositories were specified in the test request. Processing them now...")
            for repo_url in test_request_object.git_repos:
                self.logger.debug("Cloning %s..." % repo_url)
                Repo.clone_from(repo_url, os.path.abspath(self.workspace) + "/git/")

        self.perform_board_work(
                            self.control_board(
                                        self.resource_pool.get_board_by_type(test_request_object.master_board), 
                                        test_request_object.master_board,
                                        "master"), 
                            test_request_object
                            )


        
    def perform_board_work(self, board_object, test_request_object):
        # Continue work with the board
        board_object.power_on()

        # TODO: This is TEMPORARY! A bit of hardcoding here, for testing purposes.
        # Need to clarify how to differentiate between config details of the same 
        # board type.
        board_object.submit_config_params(test_request_object.nodes[board_object.get_board_role()])
        #board_object.boot_board("ramdisk") # extract this from the test request
        board_object.boot_board(test_request_object.master_boot_method)

        # Check to see if there are any tests to run
        if len(test_request_object.master_tests) > 0:
            self.logger.debug("Tests found for the master role: %s" % test_request_object.master_tests)

            # TODO: trigger test deployment & execution
        print("Deploying tests\n")
        self.logger.info("Deploying tests to %s" % board_object.get_board_name())
        self.deploy_tests(
                board_object.get_board_ip(),
                self.workspace + "/git/",
                test_request_object
                        )
        
        # Call the method that triggers the test run. Pass the both the board & the test request
        # objects.
        board_object.run_tests(test_request_object)

        if board_object.has_test_results:
            self.logger.info("Test results found. Processing...")

            # TODO: A temporary workaround in order to test out test result processing
            # changes; This needs to be fixed!
            # self.process_test_results(board_object.board_name)
            self.process_test_results2()

    #def process_request_queue(self):
    #    """Goes through the request queue and processes taks"""
    #    while True:
    #        self.request_queue.get()
    #        self.request_queue.task_done()

    def reserve_board(self, board_name, attempts = 3):
        """Perform the necessary operations for reserving the specified board. Must be moved to the ResourcePool"""
        # ----------------------------------------------------------------------- #
        # This method seems to match the desired reservation behavior. It tries   #
        # to reserve for a given number of tries and, if the operation failes,    #
        # an exception is raised.                                                 #
        # It is advisable to work on extending this (already implemented) method  #
        # and make it perform additional tasks, if needed (for example, to also   #
        # try logging on to the board in order to confirm its' operational state) #
        # ----------------------------------------------------------------------- #
        # Create a "shell" object. We use pexpect and not pxssh, because the command is passed
        #_shell = pexpect.spawn("bash")
        #_shell.logfile = logfile

        self.logger.info(self.constants.INFO["reservationattempt"] % board_name)
        reserved = False
        reservation_id = None

        reserve_cmd = self.constants.COMMANDS["reservetarget"] % (board_name, "5M")
        self.logger.debug(reserve_cmd)
        reservation_id = self.run_command(reserve_cmd)

        #for i in range(attempts):
        #    reserve_cmd = self.constants.COMMANDS["reservetarget"] % ("5M", board_name)
        #    self.logger.debug(reserve_cmd)
            #_shell.sendline(reserve_cmd)
            #found = _shell.expect(["Reservation confirmed","Reservation Exception",pexpect.TIMEOUT])
        #    reservation_id = self.run_command(reserve_cmd)
            # This is present in the original version, since commands were executed on remote machines,
            # via SSH. Omitting this in this context, since we run a local shell
            #self._shell.prompt(timeout=10)
            #if found==0:
            #    self.logger.info(self.constants.INFO["reservationconfirmed"] % board_name)
            #    reserved=True

            #    reservation_id = _shell.before[5:-2]
            #    break
            #elif found==1:
            #    self.logger.info(self.constants.INFO["targetalreadyreserved"] % board_name)

                # Here we will need to invoke our ExceptionHandler, and error triage will be
                # done there. So, whenever an exception should be raised, it will be passed
                # 'blindly' to the ExceptionHandler 
                # TODO: Use a custom exception instead of plain log errors
            #    self.logger.error(self.constants.ERRORS["targetreserved"])
            #else:
            #    self.logger.info(self.constants.INFO["targetalreadyreserved"] % (board_name, str(i)))
        #if not reserved:
        #   self.logger.info(self.constants.ERRORS["unabletoreserve"] % (board_name, attempts))

        return reservation_id

    def unreserve_board(self, board, reservation_id):
        """Erase the specified target reservation ID"""
        cmd_string = self.constants.COMMANDS["unreservetarget"] % (board, reservation_id)
        unreserve_result = self.run_command(cmd_string)

        print(self.constants.INFO["targetunreserved"] % board)

    def control_board(self, board_name, board_type, board_role):
        """This is used to get an instance of the BoardObject type, which allows one
        to directly perform operations for that board (power management, image loading, etc)"""

        # ---------------------------------------------------------------------
        # NB: We need a mechanism to check if the current user has the right to 
        # control the board, based on the reservation or on the error code 
        # that we may receive from the 'target' command
        # Now, we get a new DeviceObject instance with some attributes already
        # set. This is returned, giving one the ability to easily manage each
        # instance separately.
        # ---------------------------------------------------------------------
        
        # First, reserve the board
        self.logger.info("Attempting to reserve %s..." % board_name)
        reservation_id = self.reserve_board(board_name)

        self.logger.info("Creating a new board object...")
        new_board_object = BoardObject.DeviceObject(
                                board_name, 
                                board_type, 
                                board_role,
                                reservation_id, 
                                self.resource_pool.board_file_path, 
                                "%s/" % self.workspace
                                )
       
        return new_board_object
    
    def run_command(self, command_string):
        """Runs a command on the current machine/terminal"""
        #args = shlex.split(command_string)
        #subprocess.run([] ,stdout=subprocess.PIPE)
        self.logger.debug("Sending command %s" % command_string)
        result = subprocess.check_output(command_string, shell=True)
        return result.split(b'=')[1]

    def run_remote_command(self, host, command_array):
        """Runs a command or a list of commands on a specified remote host"""
        print("This is a stub")

    def deploy_tests(self, board_ip, test_repo, test_request_obj):
        """Used for deploying test prerequisites & test files on a board. We use SSH for this."""
        self.logger.debug("Local path that will be copied to the board: %s" % test_repo)

        # For now, we hardcode this remote path, but this parameter must be made dynamic
        remote_board_path = "/home/root"
        self.logger.info("Deploying tests found in %s to %s...." % (test_repo, board_ip))

        # First, create a BASH profile file with all the environment variables
        # to be used when remotely running the required commands
        # TODO: Remove the hardcoded file name once things get a bit sorted out
        profile_file_path = '{0}tmp/{1}'.format(self.workspace, str('env_vars'))
        with open(profile_file_path, mode='wb') as profile_file:
            for environment_var in test_request_obj.env_vars.split('\n'):
                profile_file.write(bytes(environment_var + "\n", 'UTF-8'))

        repository_file_path = '{0}tmp/{1}'.format(self.workspace, str('el-repositories.list'))
        with open(repository_file_path, mode='wb') as repos_file:
            for repo_item in test_request_obj.repos_list:
                repos_file.write(bytes("deb [trusted=yes] %s/%s/ ./" % (test_request_obj.repos_url, repo_item) + "\n", 'UTF-8'))

        # TODO: Temporary hardcoding a path
        scp_command_template = "ssh-keygen -R {0}; \
                                ssh -o StrictHostKeyChecking=no root@{1} pwd; \
                                scp -r {2} root@{3}:{4}; \
                                scp -r {5} root@{6}:{7}; \
                                scp -r {8} root@{9}:/etc/apt/sources.list.d/el-repositories.list;".format(
                                                                    board_ip,
                                                                    board_ip,
                                                                    test_repo,
                                                                    board_ip,
                                                                    remote_board_path,
                                                                    profile_file_path,
                                                                    board_ip,
                                                                    remote_board_path,
                                                                    repository_file_path,
                                                                    board_ip,
                                                                    remote_board_path
                                                                    )
        # Make files readable
        #scp_command_template = scp_command_template + " chmod -R a+x %s;" % remote_board_path
        #scp_command_template = scp_command_template + " {0}/{1};".format(remote_board_path, test_request_obj.pkg_installer)
        #scp_command_template = scp_command_template + " find %s -type d -exec chmod 755 {} \;" % remote_board_path
        scp_command_template = scp_command_template + " find %s -type f -exec chmod 644 {} \;" % remote_board_path

        result = subprocess.getoutput(
                               scp_command_template.replace("{board_ip}", board_ip)
                                )
        self.logger.debug(result)

        # Check for env
        #    self.logger.debug("Env vars:\n {0}".format(
        #        subprocess.getoutput(
        #                'ssh -o StrictHostKeyChecking=no root@%s "chmod +x ./env_vars; . ./env_vars; set;"' 
         #                % board_ip)))

        chmod_result = subprocess.getoutput(
                        'ssh -o StrictHostKeyChecking=no root@%s "chmod +x /home/root/git/lava2-playground/uboot/install_deb_package.sh"' % board_ip)
        self.logger.debug("chmod log: %s" % chmod_result)

        self.logger.debug(">>> Raw SCP log follows <<<\n %s" % result.split('\n'))
        self.logger.info("Test files copied to %s" % board_ip)


        # Installing the test packages
        # ---------------------------------
        command_string = "ssh root@{0} ".format(board_ip)

        self.logger.debug("Preparing to install test packages...")
        for test in test_request_obj.master_tests:
            self.logger.info("Installing test package: {0}".format(test))

            # For the moment, use the hardcoded env_vars profile file
            # TODO: the "touch el-repos.list" must be added to the install_deb_package.sh script
            _tmp_cmd = command_string + " 'bash -c \" source {0}/env_vars;touch /etc/apt/sources.list.d/el-repositories.list; {1}/{2} {3}\"'".format(
                                                                        remote_board_path, 
                                                                        remote_board_path, 
                                                                        test_request_obj.pkg_installer,
                                                                        test)
            
            self.logger.debug("Package installer: %s" % test_request_obj.pkg_installer)
            self.logger.debug("Test package: %s" % test)
            self.logger.debug("PKG installation command: {0}".format(_tmp_cmd))
            
            #command = _tmp_cmd.split(' ')
          
            output = subprocess.getoutput(_tmp_cmd)
            self.logger.debug("Command output: {0}".format(output))

        self.logger.info("Tests deployed to %s" % board_ip)

        # Print a console message
        print("Tests deployed to the board.\nRunning tests...")

        # ==========================================================================================
        # NOTE: The Paramiko library is not compatible with the Dropbear SSH server. 
        # Therefore, we are forced to wrap around existing system command
        # utilities in order to get past this limitation. However, code that performs all these
        # operations using Paramiko will be kept here for future reference or use, if needed.        
        #ssh = paramiko.SSHClient() 
        # Deal with host keys
        #ssh.load_system_host_keys()
        #ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        # Open an SSH connection to the board
        #ssh.connect(board_ip, username="root")

        # Obtain a SFTP client instance
        #sftp = ssh.open_sftp()

        # Parse the local folder structure and mirror it on the remote host
        # TODO: Maybe this must be a helper method, since it will most probably be called in other 
        # contexts as well
        #local_path = os.path.expanduser(test_repo)
        
        # TODO: This will need some refactoring and/or improvements in the future
        #for dirpath, dirnames, filenames in os.walk(local_path):
        #    remote_path = os.path.join(remote_board_path, dirpath[len(local_path):])
        #    self.logger.debug("Copying remote file %s ..." % remote_path)

            # If the directory does not exist on the remote host 
        #    try:
        #        sftp.listdir(remote_path)
        #    except IOError:
        #        sftp.mkdir(remote_path)

        #    for filename in filenames:
        #        sftp.put(os.path.join(dirpath, filename), os.path.join(remote_path, filename))
        
        # Close the remote session
        # sftp.close()
        # ssh.close()
        # ==========================================================================================

    def process_test_results(self, board_name):
        # TODO: Check that the operation result is positive; otherwise, take the appropriate actions
        # and signal the error(s) encountered
        self.logger.debug("Calling the ResultParser component...")

        # Import & instantiate the ResultParser component

        #result_parser = ResultParser(self.workspace + self.test_results_dir, self.workspace + self.test_results_dir)
        #self.result_parser.process_test_results()

    # ================== TEMPORARY WORKAROUND FOR RESULT PARSING ======================
    def process_test_results2(self):
        """The main method dealing with result files parsing."""
        # TODO: First parse the test results directory contents, then begin parsing
        # each individual file

        # Parse all files available at the given path.
        for result_file in os.listdir(self.workspace + self.test_results_dir):
            self.logger.debug("Processing result file: %s" % result_file)
            print("Processing result file: %s" % result_file)
            # A temporary place to store the test results that were found
            test_results = {}
            with open("{0}/{1}".format(self.workspace + self.test_results_dir, result_file), 'r') as f:
                self.logger.debug("Current file path: %s" % "{0}/{1}".format(self.workspace + self.test_results_dir, result_file))
                for line in f:
                    if ":" in line:
                        (test_suite, test_result) = line.split(":")
                        test_result = test_result.strip()
                        if test_result in ["SKIP", "PASS", "FAIL"]:
                            test_results[test_suite.strip()] = test_result
            test_suite_name = result_file.replace("_test_result", "")
            self.write_xml_file(test_results, test_suite_name)

    def write_xml_file(self, test_results, test_suite_name):
        """Used to export the test results gathered during the test run, in
        JUnit XML format"""
        xml_output = ""
        xml_output += '<?xml version="1.0" encoding="UTF-8"?>'
        xml_output += '<testsuites>'
        xml_output += '<testsuite name="{0}">'.format(test_suite_name)
        for test_name, test_result in test_results.items():
            xml_output += '<testcase name="{0}">'.format(test_name)
            if test_result == 'FAIL':
                xml_output += '<failure/>'
            elif test_result == 'SKIP':
                xml_output += '<skipped/>'
            xml_output += '</testcase>'
        xml_output += '</testsuite>'
        xml_output += '</testsuites>'
        #with open("{0}/{1}.xml".format(self.output_location, test_suite_name), "w") as f:
        with open("{0}/{1}.xml".format(self.workspace + self.test_results_dir, test_suite_name), "w") as f:
            f.write(xml_output)



class TestRequest:
    """An object used for building request objects based on the info received from the bmtf-run script.
    Once a request is parsed and data is extracted, it is forwarded to the BoardManager, which
    in turn creates a TestRequest object that will be processed by the process_test_request() method,
    in a queue, using a distinct thread."""

    def __init__(self, job_data):
        """Object constructor. We set test request attributes based on the data"""
        # When evaluating the nodes from the request, we set this to either single-node or multinode
        self.job_type = ""

        self.job_data = job_data

        # A simple dictionary that holds each node name and its role and the rest of the parameters
        self.nodes = {} 

        # An array to keep the names of boards acting as slaves in a multinode scenario
        self.slave_boards = []

        # Obey thy master board :)
        self.master_board = ""

        # Array to store the custom environment variables we might find. 
        self.env_vars = ""

        # Store the test repos that are specified in the test request
        self.git_repos = []

        # Store the test repositories
        self.repos_list = []
        self.repos_url = ""

        # Array used to store tests that will be run on the master
        self.master_tests = []

        # The script / command used for installing test packages
        self.pkg_installer = ""

        self.master_boot_method = ""

        # If we are dealing with an IPMI-managed board that does not provide direct access
        # to the bootloader, we must go a different path
        self.ipmi_toolkit = {}

        # Run integrated methods for test request parsing
        self.determine_test_type()
        self.extract_node_configuration()
        self.get_master_boot_method()
        self.extract_test_info()

    def determine_test_type(self):
        """Determine wether or not this is a multinode scenario"""

        for board_role, board_type in self.job_data["boards"].items():
            # If we find a master role, set master_board to that board's name
            # TODO: implement a simple sanity check for the submitted request.
            # For example, if the JSON contains two master entries, an error
            # must be returned, so that the BMTF servers send back a "400 BAD 
            # REQUEST"
            if board_role == "master":
                self.master_board = board_type

            # Slaves count (if any)
            if board_role == "slave":
                self.slave_boards.append(board_type)

        # If no slaves have been set, then this is a single-node test
        # TODO: This really needs to rely on a JSON sanity check
        if self.master_board != "" and len(self.slave_boards) == 0:
            self.job_type = "single-node"
        else:
            self.job_type = "multinode"

    def extract_node_configuration(self):
        """Extract information regarding the implied nodes"""
        # Add the node to our nodes dictionary, along with "instance_config"
        for board_role, board_instance_config in self.job_data["instance_config"].items():
            #self.nodes.update({board_type : board_instance_config})
            self.nodes.update({board_role : board_instance_config})

    def get_master_boot_method(self):
        """Determine the boot method to be used for the master board"""
        self.master_boot_method = self.job_data["instance_config"]["master"]["boot_method"]

    def extract_test_info(self):
        """Used for extracting info about the tests that will be run, along with others related
        to the test run: Git repositories, specific environment variables, etc."""
        for section, section_contents in self.job_data["tests"].items():
            if section == "toolkit":
                self.git_repos.append(section_contents["git_repos"])
                self.env_vars = '\n'.join(section_contents["env_vars"])
                #self.env_vars.append(section_contents["env_vars"])
                self.pkg_installer = section_contents["package_installer"]
                self.repos_url= section_contents["package_repository_url"]
                self.repos_list = section_contents["repository_list"].split(' ')

            if section == "master":
                # Extract the tests to be run on the master board. 
                # TODO: For now, we only offer single-node testing, but this method
                # will be extended once we start implementing multinode testing 
                # support
                for test_name in section_contents:
                    self.master_tests.append(test_name)

