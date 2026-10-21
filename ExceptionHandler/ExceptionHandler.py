import logging


class ExceptionHandler:
    """Used for handling errors encountered while running our tools. This
    provides a uniform manner of treating errors"""

    def __init__(self, logger=None):
        """Object constructor"""
        self.status = "ready"
        self.last_exception = None
        self.logger = logger or logging.getLogger("damf.exceptions")

    def handle(self, exc, reraise=False):
        """Log and record an exception."""
        self.status = "error"
        self.last_exception = exc
        self.logger.error("DAMF Exception [%s]: %s", type(exc).__name__, exc)
        if reraise:
            raise exc
        return {
            "type": type(exc).__name__,
            "message": str(exc),
        }
