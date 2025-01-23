from typing import Literal

from notte.errors.base import ErrorConfig, ErrorMessageMode


def set_error_mode(mode: Literal["developer", "user"]) -> None:
    """Set the error message mode for the package.

    Args:
        mode: Either 'developer' or 'user'
    """
    ErrorConfig.set_message_mode(mode)


# Default to user mode
ErrorConfig.set_message_mode(ErrorMessageMode.DEVELOPER.value)
