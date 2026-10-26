import sys
import warnings
from importlib import metadata

from notte_core.errors import ErrorConfig, ErrorMessageMode, ErrorMode
from notte_core.logging import logger

__version__ = metadata.version("notte_core")


def set_error_mode(mode: ErrorMode) -> None:
    """Set the error message mode for the package.

    Args:
        mode: Either 'developer', 'user' or 'agent'
    """
    ErrorConfig.set_message_mode(mode)


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
set_logger_mode("agent")

nest_asyncio_enabled: bool = False


def enable_nest_asyncio() -> None:
    """Deprecated: Notte sync methods no longer need nested event loops."""
    warnings.warn(
        "enable_nest_asyncio() is deprecated and has no effect; Notte no longer patches asyncio.",
        DeprecationWarning,
        stacklevel=2,
    )


from notte_core import _v1_aliases as _v1_aliases  # noqa: E402
