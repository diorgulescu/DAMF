import subprocess
import logging
import pexpect
import sys
import yaml

class DeviceObject:
    """Used as a helper for the BoardManager class, in order to provide a way to easily
    manage board-level operations, like flashing, reflashing, power cycle management and
    other tasks. Uses pexpect for bootloader interaction"""
    def __init__(self, board_id, board_type, board_role, res_id, boardfile_path, workspace_dir, board_info=''):
        self.board_name = board_id
        self.board_type = board_type
        self.board_info = board_info
        self.board_role = board_role
        self.board_ip = ""
        self.reservation_id = res_id
        self.boardfile_path = boardfile_path
        self.attributes = {} # This MUST be renamed to something else, since it's ambiguous as hell...
        self.ramdisk_commands = []
        self.nfs_commands = []
        self.workspace = workspace_dir

        # Board attributes
        self.has_ssh = False
        self.ipmi_managed = False
        self.ipmi_tools = {}

        # IVLab-compatible attributes
        self.arch = ""
        self.nb_of_eth_ports = ""
        self.bootloader = ""
        self.ivlab_id = ""
        self.cpu = ""
                
        self.has_test_results = False

         # We create our logger, including a formatter
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.DEBUG)
        #logfile_handler = logging.FileHandler(log_dir + board_id + ".log")
        logfile_handler = logging.FileHandler(self.workspace + "/logs/%s.log" % board_id)
        formatter = logging.Formatter('%(asctime)s[%(levelname)s] %(message)s',datefmt='[%m/%d/%Y][%H:%M:%S]')
        logfile_handler.setFormatter(formatter)
        self.logger.addHandler(logfile_handler)

        self.logger.debug("Created BoardObject for %s" % self.board_name)
        self.logger.debug("Reading device file")

        # Perform initial object "setup"
        self.read_device_file(self.board_type)
        self.get_ivlab_board_info()
        
    # ATTRIBUTE SETTERS AND GETTERS
    def get_board_name(self):
        """Returns the board name as set for the current object instance"""
        return self.board_name

    def set_board_name(self, new_board_name):
        """Use this to change the board name for this object instance"""
        self.board_name = new_board_name

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
        """Return board info (as in IVLab)"""
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

    # METHODS
    # since we are working on a LAVA replacement, the code written by adgh
    # will be added here, and altered so that hardcoded strings are migrated to the 
    # Constants class and things will be split as better as possible.
    # Notes and implementation ideas:
    # - since the "child" object is held and used for managing the pexpect connection,
    # this should be passed along between methods, so that we never disconnect from the board
    # unless the tests we run are done.
    # - once the board has been successfully booted, we should return the connection
    # object back to the BoardManager, so that further operations can be performed

    def reset(self):
        """Used to call a reset on the board represented by the current object instance"""
        return("Momentarily, this is a stub")

    def power_off(self):
        """Power off the board"""
        # Must see if it is advisable to also reserve the board when performing power off.
        # Maybe a single reservation should be made, and the ID could be passed to the constructor
        # of the current object. Must decide upon the most efficient and streamlined approach
        print("Momentarily, this is a stub")

    def power_on(self):
        """Bring the board power up"""
        # In case we ever need to manage IPMI boards, we must extend this in order to 
        # pass ipmi-tool commands. These also require some credentials, and we will deal
        # with the whole scenario when and if we need/want to.
        #subprocess.call("target %s -r now-+5M" % (self.board_name),shell=True)
        self.logger.info("Powering on...")
        subprocess.call("target %s -p on" % (self.board_name),shell=True)
        self.logger.info("Board successfully powered on")

    def submit_config_params(self, params_dict):
        """Receive instance configuration details in the form of a dictionary and applies
        the data to the configuration of the current object"""
        for config_section, settings in params_dict.items():
            # We use list comprehension to perform placeholder replacements more efficiently
            if config_section == "ramdisk":
                self.ramdisk_commands = [cmd.replace('{IMAGE}', settings["kernel"]) for cmd in self.ramdisk_commands]
                self.ramdisk_commands = [cmd.replace('{DTB}', settings["dtb"]) for cmd in self.ramdisk_commands]
                self.ramdisk_commands = [cmd.replace('{ROOT_FS}', settings["rootfs"]) for cmd in self.ramdisk_commands]

            if config_section == "nfs":
                self.nfs_commands = [cmd.replace('{IMAGE}', settings["kernel"]) for cmd in self.nfs_commands]
                self.nfs_commands = [cmd.replace('{DTB}', settings["dtb"]) for cmd in self.nfs_commands]
                self.nfs_commands = [cmd.replace('{ROOT_FS}', settings["rootfs"]) for cmd in self.nfs_commands]
    def get_ivlab_board_info(self):
        """Obtain details about the board in question by interogating IVLab."""
        
        self.arch = subprocess.getoutput("targetadmin --display --name %s | awk '{print $7}'" % self.board_name).split('\n')[2]
        self.nb_of_eth_ports = subprocess.getoutput("targetadmin --display --name %s | awk '{print $5}'" % self.board_name).split('\n')[2]
        self.bootloader = subprocess.getoutput("targetadmin --display --name %s | awk '{print $8}'" % self.board_name).split('\n')[2]
        self.cpu = subprocess.getoutput("targetadmin --display --name %s | awk '{print $9}'" % self.board_name).split('\n')[2]
        self.ivlab_id = subprocess.getoutput("targetadmin --display --name %s | awk '{print $2}'" % self.board_name).split('\n')[2]

        self.logger.debug("IVLab board attributes:")
        self.logger.debug("Arch: {0}\n \
                           Eth ports: {1}\n \
                           Bootloader: {2}\n \
                           CPU: {3}\n \
                           IVLab ID: {4}\n".format(self.arch, self.nb_of_eth_ports, self.bootloader, self.cpu, self.ivlab_id)
                           )

    def read_device_file(self, board_type):
        """Used for loading and reading the contents of the board's device file, which
        contains info such as boot parameters, addresses and specific commands.
        Appends the info extracted from the devfiles to the object attributes, alongside
        information fetched from IVLab"""
        self.logger.debug("Parsing board file for %s" % board_type)
        file_stream = open(r"%s%s.yml" % (self.boardfile_path, board_type))
        board_file = yaml.load_all(file_stream)

        # TODO: Design a better and more optimal algorithm for processing board_file
        # entries
        for entry in board_file:
            for section, section_contents in entry.items():
                if section == "commands":
                    for command_type, commands in section_contents.items():
                        if command_type == "ramdisk_boot":
                            for cmd in commands:
                                self.ramdisk_commands.append(cmd)

                        if command_type == "nfs_boot":
                            for cmd in commands:
                                self.nfs_commands.append(cmd)
                                self.logger.debug("NFS command: %s" % cmd)
                
                if section == "attributes":
                    for setting, value in section_contents.items():
                        if setting == "root_prompt":
                            self.root_prompt = value
                        
                        if (setting == "has_ssh" and value == "yes"):
                            self.has_ssh = True

                        if (setting == "ipmi_managed" and value == "yes"):
                            self.ipmi_managed = True

                # If dealing with an IPMI-managed board that does not provide direct access
                # to the bootloader, we must take a different approach
                if (section == "commands" and self.ipmi_managed == True):
                    _tmp_dict = {}
                    for ipmi_block, settings in section_contents.items():
                        if ipmi_block == "ipmi_managed":
                            for key, value in settings.items():
                                _tmp_dict.update({key : value})
                    self.ipmi_tools.update(_tmp_dict)

    def write_ifconfig_to_file(self, expect_object, file_path):
        """If the deployed OS has SSH support, we obtain the IP address of that device
        and pass it on to the pxssh handle. For this to work, we write the IP to a 
        file."""
        # TODO: Check the need to keep this method, considering the current approach
        with open(file_path, 'w') as f:
            expect_object.logfile = f
            expect_object.sendline("ifconfig eth0")  # try to get IP
            expect_object.expect("root@raspberrypi3-64:~#")
            # close connection to u-boot
            expect_object.sendcontrol("]")

    def boot_board(self, boot_method):
        """Since this is specific to the ENEA Lab environment, we will use the target tool"""
        self.logger.info("Booting board...")

        # If the board is IPMI-managed, we need to use a different way of booting it.
        if self.ipmi_managed == True:
            # Configure and boot the board using the extracted IPMI settings
            self.logger.debug("Running the board setup script...")
            setup_result = subprocess.getoutput(self.ipmi_tools["setup_script"])
            # TODO: parse result for errors
        else:
            child = pexpect.spawnu("target %s" % self.board_name)
            child.logfile = sys.stdout
            uboot_login = False
            root_login = False
            os_console = False
            while True:
                try:
                    i = child.expect(["Connection to .* closed.", "Quit: Ctrl", "U-Boot>", "raspberrypi3-64 login:", "root@raspberrypi3-64:~#"])
                    if i == 0:
                        self.logger.error("Board unavailable")
                        break
                    if i == 1:
                        child.sendline("")
                    if i == 2:
                        uboot_login = True
                        break
                    if i == 3:
                        root_login = True
                        break
                    if i == 4:
                        os_console = True
                        break
                except pexpect.EOF:
                    break

            if uboot_login:
                if boot_method == "ramdisk":
                    self.logger.info("Booting board using ramdisk...")
                    self.logger.debug("Raw boot commands: \n %s \n >>> END" % self.ramdisk_commands)
                    self._boot_command_sender(child, self.ramdisk_commands)
                if boot_method == "nfs":
                    self.logger.info("Booting board using NFS...")
                    self.logger.debug("Raw boot commands: \n %s \n >>> END" % self.nfs_commands)
                    self._boot_command_sender(child, self.nfs_commands)

                # login to board OS
                child.expect("raspberrypi3-64 login: ", timeout=120)
                child.sendline("root")
                child.expect("root@raspberrypi3-64:~#")
                #self.write_ifconfig_to_file(child, "target_ifconfig")
                self.write_ifconfig_to_file(child, "%s/%s_ifconfig" % (self.workspace, self.board_name))

                # Extract the IP address from the file
                #_temp_board_ip = subprocess.check_output(
                #                                        "cat %s/%s_ifconfig | grep \"inet addr:\" | awk {'print $2'}" 
                #                                            % (self.workspace, self.board_name), 
                #                                        shell=True
                #                                        )
                                                        #.split(b':')[1]
                #_temp_board_ip = str(_temp_board_ip.replace("addr:", "")).rstrip('\n')
            # _temp_board_ip = str(_temp_board_ip.rstrip('\n'))
                #self.board_ip = _temp_board_ip.replace("addr:", "").replace("\n", "")
                self.board_ip = subprocess.getoutput("cat %s/%s_ifconfig | grep \"inet addr:\" | awk {'print $2'}" 
                                                            % (self.workspace, self.board_name)).split()[0].replace("addr:", "")
                self.logger.debug("IP address for %s: %s" % (self.board_name, self.board_ip))

            if root_login:
                # login to board OS
                print("debug: got to root login")
                child.sendline("root")
                child.expect("root@raspberrypi3-64:~#")
                #self.write_ifconfig_to_file(child, "%s/%s_ifconfig" % (self.workspace, self.board_name))
                self.write_ifconfig_to_file(child, "%s/%s_ifconfig" % (self.workspace, self.board_name))

            if os_console:
                #self.write_ifconfig_to_file(child, "target_ifconfig")
                self.write_ifconfig_to_file(child, "%s/%s_ifconfig" % (self.workspace, self.board_name))

                if self.has_ssh:
                    print("test")

            #child.close()
            # Here we return the "child" object, so that the caller
            # can forward it to other procedures, mainaining an active 
            # connection with the board
            # The U-Boot instructions differ in some aspects, but not that
            # big of a difference
            return child

    def run_tests(self, test_request_obj):
        """Used for invoking the available tests. Receives the test request object and, based 
        on the contents, passes the suitable directives"""
        if self.ipmi_managed == True:
            for test in test_request_obj.master_tests:
                self.logger.info("Running test %s..." % test)
                self.logger.info("Currently running: %s" % test)
                test_run_result = subprocess.getoutput("{0} -c {1}".format(self.ipmi_tools["remote_command_runner"],
                                                                             test))
        else:
            command_string_template = "ssh root@{board_ip} \"bash -c 'source ./env_vars; %s | tee %s_test_result'\""
            command_string_template = command_string_template.replace("{board_ip}", self.board_ip)

            for test in test_request_obj.master_tests:
                self.logger.debug(command_string_template % (test, test))
                test_run_result = subprocess.getoutput(command_string_template % (test, test))

        # Once the tests have been run, call the test result extraction procedure
        self.extract_test_results()                
        
    def extract_test_results(self):
        """Used for copying test result files back to the BMTF host, for further processing."""
        status = False
        cmd_string = "scp root@{board_ip}:/home/root/*_test_result %s" % self.workspace + "test_results/"
        cmd_string = cmd_string.replace("{board_ip}", self.board_ip)

        self.logger.debug("Test result copying command: {0}".format(cmd_string))
        test_fetch_result = subprocess.getstatusoutput(cmd_string)
        
        if test_fetch_result[0] == 0:
            self.has_test_results = True
            status = True
        else:
            self.logger.error("No test results found!")
        return status

    def _boot_command_sender(self, child, command_list):
        """Helper method for parsing the available commands, splitting them in chunks
        and forwarding them to the pexpect session object"""
        number_of_commands = len(command_list)
        for command in command_list:
            command_index = command_list.index(command)
            for command_chunk in command.split(" "):
                child.send("%s " % command_chunk)
            child.sendline("")
            if (command_index < number_of_commands - 1):
                child.expect("U-Boot>")
        return child