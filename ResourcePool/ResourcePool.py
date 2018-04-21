import subprocess
import yaml
import os
import sys

class ResourcePool:
    """Used for managing the boards currently available within the test laboratory. Makes sure that
    all resource requests are served from one specific source."""
    def __init__(self, board_files_path, logger_handle):
        """Object constructor"""
        self.logger = logger_handle

        # A dictionary used to store the boards available for our tests
        self.available_boards = {}

        # The absolute path to the folder containing all our board files.
        self.board_file_path = board_files_path

        # A vector to hold the board types we can work with
        self.board_types = []

    def get_board_by_type(self, board_type):
        print("Stub")

    def find_available_boards(self):
        print("Stub")

    def find_board_types(self):
        print("Stub")
        self.logger.info("Done reading available board files")
