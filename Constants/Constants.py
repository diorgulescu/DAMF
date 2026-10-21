import os
import xml.etree.ElementTree as ET

from damf.config import safe_load_yaml


class Constants:
    """Provides access to the constants we are using throughout our tools.
    More specifically, it uses an INI-like XML or YAML file as its data source."""

    def __init__(self, constantsFile=None):
        """Constants object constructor. Defines dictionaries used to hold various
        constants (strings, messages, credentials, etc.)"""
        base_dir = os.path.dirname(os.path.realpath(__file__))
        if constantsFile is None:
            constantsFile = os.path.join(base_dir, "Constants.xml")
        self.constants_file = constantsFile
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

        if os.path.exists(self.constants_file):
            if self.constants_file.endswith((".yml", ".yaml")):
                self._extract_constants2()
            else:
                self.tree = ET.ElementTree(file=self.constants_file)
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
            if constant.tag == "error":
                self.ERRORS.update({name: message_body})

            if constant.tag == 'command':
                self.COMMANDS.update({name: message_body})

            if constant.tag == 'prompt':
                self.PROMPTS.update({name: message_body})

            if constant.tag == 'warning':
                self.WARNINGS.update({name: message_body})

            if constant.tag == 'auth':
                self.CREDENTIALS.update({name: message_body})

            if constant.tag == 'loadcmd':
                self.IMAGELOADING.update({name: message_body})

            if constant.tag == 'info':
                self.INFO.update({name: message_body})

            if constant.tag in ('db', 'database'):
                self.DB.update({name: message_body})

            if constant.tag == 'url':
                self.URL.update({name: message_body})

            if constant.tag == 'path':
                self.PATH.update({name: message_body})

    def _extract_constants2(self):
        """Constant extractor for YAML constants file"""
        with open(self.constants_file, "r", encoding="utf-8") as fh:
            data = safe_load_yaml(fh) or {}
        self.ERRORS.update(data.get("errors", {}))
        self.INFO.update(data.get("info", {}))
        self.COMMANDS.update(data.get("commands", {}))

    # Methods for accessing object properties
    # It remains to be seen if this are really necessary since we can
    # directly invoke the exposed dictionaries
    def get_error(self, error_name):
        return self.ERRORS[error_name]
