from enum import Enum
from typing import Literal


class ErrorMessageMode(Enum):
    DEVELOPER = "developer"
    USER = "user"


class ErrorConfig:
    _message_mode: ErrorMessageMode = ErrorMessageMode.DEVELOPER

    @classmethod
    def set_message_mode(cls, mode: Literal["developer", "user"]) -> None:
        if mode not in [ErrorMessageMode.DEVELOPER.value, ErrorMessageMode.USER.value]:
            raise ValueError(f"Invalid message mode: {mode}")
        cls._message_mode = ErrorMessageMode(mode)

    @classmethod
    def get_message_mode(cls) -> ErrorMessageMode:
        return cls._message_mode

    @classmethod
    def is_developer_mode(cls) -> bool:
        return cls._message_mode == ErrorMessageMode.DEVELOPER


class NotteBaseError(ValueError):
    """Base exception class for all package errors."""

    TRY_AGAIN_LATER_MESSAGE: str = " Please try again later."
    NOTTE_TEAM_NOTIFIED_MESSAGE: str = "Our team has been notified of the issue. We will fix it as soon as possible."

    def __init__(
        self,
        dev_message: str,
        user_message: str,
        should_retry_later: bool = False,
        should_notify_team: bool = False,
    ) -> None:
        self.dev_message: str = dev_message
        self.user_message: str = user_message
        self.should_retry_later: bool = should_retry_later
        self.should_notify_team: bool = should_notify_team
        # Use the appropriate message based on the mode
        if ErrorConfig.is_developer_mode():
            message = self.dev_message
        elif self.should_notify_team:
            message = f"{self.user_message} {self.NOTTE_TEAM_NOTIFIED_MESSAGE}"
        else:
            message = self.user_message
        if self.should_retry_later:
            message += f" {self.TRY_AGAIN_LATER_MESSAGE}"
        super().__init__(message)


class NotteTimeoutError(NotteBaseError):
    def __init__(self, message: str) -> None:
        super().__init__(dev_message=message, user_message=message, should_retry_later=True)


class UnexpectedBehaviorError(NotteBaseError):
    def __init__(self, message: str, advice: str) -> None:
        super().__init__(
            dev_message=f"Unexpected behavior: {message}. {advice}",
            user_message="Something unexpected happened.",
            should_notify_team=True,
        )
