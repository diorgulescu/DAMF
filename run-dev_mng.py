import os
import sys
import yaml
from optparse import OptionParser

# Append the current folder to the system path. We do this in order to be able to call 
# components directly in test environments.
try:
	sys.path.append(os.path.dirname(os.path.realpath(__file__)))
	from DeviceManager import DeviceManager
except ImportError:
	raise ImportError("Could not import the DeviceManager component")

def main(argv):
    """Used for calling the components in a very narrow, test flow"""
    parser = OptionParser()
    parser.add_option("-y", "--yaml-file", dest="yaml_file",
			action="store", type="string",
			help="Supply the absolute path to the YAML file describing you test request", metavar="TEST_REQUEST")
    parser.add_option("-c", "--config-file", dest="cfg_file",
			action="store", type="string",
			help="The location of the framework config file (in YAML format)", metavar="CONFIG_FILE")
    parser.add_option("-d", "--enable-debugging", dest="debug",
            action="store_true", help="Enable debug log messages")

    (options, args) = parser.parse_args()

    if not options.yaml_file:   
    	parser.error('No YAML file specified! Use -h for more instructions.')
    	sys.exit(2)
	
    if not options.cfg_file:   
    	parser.error('The config file has not been specified.Use -h for more instructions.')
    	sys.exit(2)

    print("Starting a new run...")
    if options.debug == True:
        dev_manager = DeviceManager.DeviceManager(options.cfg_file, True)
        dev_manager.submit_test_request(extract_yaml(options.yaml_file))
    else:
        dev_manager = DeviceManager.DeviceManager(options.cfg_file)
        dev_manager.submit_test_request(extract_yaml(options.yaml_file))

def extract_yaml(yaml_file_path):
	"""Parse the given YAML test request, extract the data and forward it to the Device
	Manager component"""
	file_stream = open(yaml_file_path)
	yaml_content = yaml.load(file_stream)

	# TODO: Perform additional tasks here in order to sanitize the input
	return yaml_content

if __name__ == "__main__":
	# Run flow
	main(sys.argv[1:])