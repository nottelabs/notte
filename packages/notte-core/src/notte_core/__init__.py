from importlib import metadata

from notte_core.errors.base import ErrorConfig, ErrorMessageMode, ErrorMode

__version__ = metadata.version("notte_core")


def set_error_mode(mode: ErrorMode) -> None:
    """Set the error message mode for the package.

    Args:
        mode: Either 'developer', 'user' or 'agent'
    """
    ErrorConfig.set_message_mode(mode)


def check_notte_version(package_name: str) -> str:
    package_version = metadata.version(package_name)
    if __version__ != package_version:
        raise ValueError(
            f"Version mismatch between notte_core and {package_name}: {__version__} != {package_version}. Please update your packages."
        )
    return package_version


# Default to user mode
ErrorConfig.set_message_mode(ErrorMessageMode.DEVELOPER.value)

# Initialize telemetry
# This import only initializes the module, actual tracking will be disabled
# if ANONYMIZED_TELEMETRY=false is set or if PostHog is not installed
from notte_core.common import telemetry  # type: ignore # noqa
