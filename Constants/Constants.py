import xml.etree.cElementTree as ET
import yaml

class Constants:
    """Provides access to the constants we are using throughout our tools.
    More specifically, it uses an INI-like file as it's data source."""

    def __init__(self, constantsFile = '/homes/drio/git.enea.se/current_work/lava-replacement/target_manager/Constants/Constants.xml'):
        """Constants object constructor. Defines dictionaries used to hold various
        constants (strings, messages, credentials, etc.)"""
        self.tree = ET.ElementTree(file=constantsFile)
        self.ERRORS = {}
        self.WARNINGS = {}
        self.PROMPTS = {} 
        self.COMMANDS = {}
        self.CREDENTIALS = {}
        self.INFO = {}
        self.IMAGELOADING = {}
        self.DB = {}
        self.URL = {}
        self.PATH = {}

        self._extract_constants()

    def _extract_constants(self):
        """Invoked while the object is initialised. Parses the loaded XML tree,
        extracts constants and adds them to the appropriate constant dictionaries"""
        for constant in self.tree.iter():
            name = constant.get('name')
            message_body = constant.get('string')

            # TODO
            # When dealing with error messages, it would be advisable to have
            # a distinct set of attributes for each XML element defining an 
            # error message, that would help treating it more "granularly",
            # i.e. take a course of action based on a specific attribute, 
            # like 'severity' or 'resolution' (the latter refers to a keyword
            # suggesting a way to deal with the context)
#            severity = constant.get('severity')
#            resolution = constant.get('resolution')
            if constant.tag == "error":
                self.ERRORS.update({ name : message_body})

            if constant.tag == 'command':
                self.COMMANDS.update({ name : message_body})

            if constant.tag == 'prompt':
                self.PROMPTS.update({ name : message_body})                                               

            if constant.tag == 'warning':
                self.WARNINGS.update({ name : message_body})                                

            if constant.tag == 'auth':
                self.CREDENTIALS.update({ name : message_body })

            if constant.tag == 'loadcmd':
                self.IMAGELOADING.update({ name : message_body })

            if constant.tag == 'info':
                self.INFO.update({ name : message_body })

            if constant.tag == 'db':
                self.DB.update({ name : message_body })

            if constant.tag == 'url':
                self.URL.update({ name : message_body })

            if constant.tag == 'path':
                self.PATH.update({ name : message_body })


    def _extract_constants2(self):
        """Constant extractor"""
        # Sketch for using YAML constants file
    # Methods for accessing object properties
    # It remains to be seen if this are really necessary since we can
    # directly invoke the exposed dictionaries
    def get_error(self, error_name):
        return self.ERRORS[error_name]

