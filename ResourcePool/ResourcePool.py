import logging
import os

from damf.pool import ResourcePool as _CoreResourcePool


class ResourcePool(_CoreResourcePool):
    """Used for managing the boards currently available within the test laboratory. Makes sure that
    all resource requests are served from one specific source."""

    def __init__(self, board_files_path="", logger_handle=None, db_path=":memory:"):
        """Object constructor"""
        super().__init__(
            db_path=db_path,
            board_files_path=board_files_path or None,
            logger_handle=logger_handle or logging.getLogger(__name__),
        )
        if not self.list_devices():
            self.seed_demo_devices()
