from damf.results import ResultParser as _CoreResultParser


class ResultParser(_CoreResultParser):
    """Used for processing and exporting test results into various formats"""

    def __init__(self, result_file_path=".", report_output_path=None):
        """Object constructor"""
        super().__init__(result_file_path=result_file_path, report_output_path=report_output_path)
