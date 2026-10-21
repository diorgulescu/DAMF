from optparse import OptionParser
import os
import sys

# Append the current folder to the system path. We do this in order to be able to call
# components directly in test environments.
sys.path.append(os.path.dirname(os.path.realpath(__file__)))
from DeviceManager import DeviceManager
from damf.config import safe_load_yaml


def main(argv):
    """Used for calling the components in a very narrow, test flow"""
    parser = OptionParser()
    parser.add_option(
        "-y",
        "--yaml-file",
        dest="yaml_file",
        action="store",
        type="string",
        help="Supply the absolute path to the YAML file describing your test request",
        metavar="TEST_REQUEST",
    )
    parser.add_option(
        "-c",
        "--config-file",
        dest="cfg_file",
        action="store",
        type="string",
        help="The location of the framework config file (in YAML format)",
        metavar="CONFIG_FILE",
    )
    parser.add_option(
        "-d",
        "--enable-debugging",
        dest="debug",
        action="store_true",
        help="Enable debug log messages",
    )

    (options, _args) = parser.parse_args(argv)

    if not options.yaml_file:
        parser.error("No YAML file specified! Use -h for more instructions.")

    if not options.cfg_file:
        parser.error("The config file has not been specified. Use -h for more instructions.")

    print("Starting a new run...")
    dev_manager = DeviceManager.DeviceManager(options.cfg_file, bool(options.debug))
    dev_manager.submit_test_request(extract_yaml(options.yaml_file))


def extract_yaml(yaml_file_path):
    """Parse the given YAML test request, extract the data and forward it to the Device
    Manager component"""
    with open(yaml_file_path, "r", encoding="utf-8") as file_stream:
        return safe_load_yaml(file_stream)


if __name__ == "__main__":
    main(sys.argv[1:])
