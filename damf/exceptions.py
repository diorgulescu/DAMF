"""Custom exceptions for the Device Automation and Management Framework (DAMF)."""


class DAMFError(Exception):
    """Base exception for all DAMF errors."""


class ConfigurationError(DAMFError):
    """Raised when a configuration or request file is invalid or missing."""


class DeviceNotFoundError(DAMFError):
    """Raised when no matching device exists in the resource pool."""


class ReservationError(DAMFError):
    """Raised when a device reservation fails or is invalid."""


class DeviceBusyError(ReservationError):
    """Raised when attempting to reserve or control a device owned by another user."""


class TransportError(DAMFError):
    """Raised when communication over SSH, Serial, or ADB fails."""


class CommandTimeoutError(TransportError):
    """Raised when a command executed on a device times out."""


class PowerControlError(DAMFError):
    """Raised when a power controller fails to change or query board power state."""


class ImageLoadFailed(DAMFError):
    """Raised when loading a kernel, DTB, rootfs, or firmware image onto a target fails."""

    def __init__(self, image_name: str, path: str = "", target: str = "", msg: str | None = None):
        if msg is None:
            msg = f"Failed to load image '{image_name}' onto target '{target}' from '{path}'"
        super().__init__(msg)
        self.imageName = image_name
        self.image_name = image_name
        self.path = path
        self.target = target
