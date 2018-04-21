import sys
import os

class ResultParser:
    """Used for processing and exporting test results into various formats"""
    def __init__(self, result_file_path, report_output_path):
        """Object constructor"""
        self.result_file_path = result_file_path
        self.output_location = report_output_path
        #self.logger = logger_handle

    def process_test_results(self):
        """The main method dealing with result files parsing."""
        # TODO: First parse the test results directory contents, then begin parsing
        # each individual file
        print("Stub")

    def write_junit_xml(self, test_results, test_suite_name):
        """Used to export the test results gathered during the test run, in
        JUnit XML format"""
        xml_output = ""
        xml_output += '<?xml version="  1.0" encoding="UTF-8"?>'
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
        with open("{0}/{1}.xml".format(self.output_location, test_suite_name), "w") as f:
            f.write(xml_output)