from notte.errors.base import ErrorConfig, ErrorMessageMode, ErrorMode


def set_error_mode(mode: ErrorMode) -> None:
    """Set the error message mode for the package.

    Args:
        mode: Either 'developer', 'user' or 'agent'
    """
    ErrorConfig.set_message_mode(mode)


# Default to user mode
ErrorConfig.set_message_mode(ErrorMessageMode.DEVELOPER.value)
