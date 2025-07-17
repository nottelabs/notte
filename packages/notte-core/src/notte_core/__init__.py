import os
import sys
from importlib import metadata

from loguru import logger

from notte_core.errors.base import ErrorConfig, ErrorMessageMode, ErrorMode

__version__ = metadata.version("notte_core")


def set_error_mode(mode: ErrorMode) -> None:
    """Set the error message mode for the package.

    Args:
        mode: Either 'developer', 'user' or 'agent'
    """
    ErrorConfig.set_message_mode(mode)


class LoggingSetup:
    @staticmethod
    def set_logger_mode(mode: ErrorMode) -> None:
        match ErrorMessageMode(mode):
            case ErrorMessageMode.DEVELOPER:
                format = "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
                _ = logger.configure(handlers=[dict(sink=sys.stderr, level="DEBUG", format=format)])  # pyright: ignore [reportArgumentType]
            case ErrorMessageMode.AGENT | ErrorMessageMode.USER:
                format = "<level>{level: <8}</level> - <level>{message}</level>"
                logger.configure(handlers=[dict(sink=sys.stderr, level="INFO", format=format)])  # type: ignore


def check_notte_version(package_name: str) -> str:
    package_version = metadata.version(package_name)
    core_version = metadata.version("notte_core")
    if core_version != package_version:
        raise ValueError(
            f"Version mismatch between notte_core and {package_name}: {core_version} != {package_version}. Please update your packages."
        )
    return package_version


# Default to agent mode
set_error_mode("developer")
LoggingSetup.set_logger_mode("agent")

# Initialize telemetry
# This import only initializes the module, actual tracking will be disabled
# if DISABLE_TELEMETRY is set or if PostHog is not installed
from notte_core.common import telemetry  # type: ignore # noqa

nest_asyncio_enabled: bool = False


def enable_nest_asyncio() -> None:
    """Enable nested event loops (required for Jupyter). Stores state if already enabled."""
    global nest_asyncio_enabled
    if nest_asyncio_enabled:
        return
    import nest_asyncio  # pyright: ignore[reportMissingTypeStubs]

    if os.environ.get("NOTTE_ENABLE_NEST_ASYNCIO", "true") == "true":
        _ = nest_asyncio.apply()  # pyright: ignore[reportUnknownMemberType]
        nest_asyncio_enabled = True
