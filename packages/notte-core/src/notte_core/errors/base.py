import contextlib
from enum import Enum
from typing import ClassVar, Literal


class ErrorMessageMode(Enum):
    DEVELOPER = "developer"
    USER = "user"
    AGENT = "agent"


ErrorMode = Literal["developer", "user", "agent"]


class ErrorConfig:
    _message_mode: ClassVar[ErrorMessageMode] = ErrorMessageMode.DEVELOPER
    _mode_stack: ClassVar[list[ErrorMode]] = []

    @classmethod
    def set_message_mode(cls, mode: ErrorMode) -> None:
        if mode not in [mode.value for mode in ErrorMessageMode]:
            raise ValueError(f"Invalid message mode: {mode}. Valid modes are: {list(ErrorMessageMode)}")
        cls._message_mode = ErrorMessageMode(mode)

    @classmethod
    @contextlib.contextmanager
    def message_mode(cls, mode: ErrorMode):
        cls._mode_stack.append(cls._message_mode.value)
        cls.set_message_mode(mode)
        try:
            yield
        finally:
            cls.set_message_mode(cls._mode_stack.pop())

    @classmethod
    def get_message_mode(cls) -> ErrorMessageMode:
        return cls._message_mode


class NotteBaseError(ValueError):
    """Base exception class for all package errors."""

    TRY_AGAIN_LATER_MESSAGE: str = " Please try again later."
    NOTTE_TEAM_NOTIFIED_MESSAGE: str = "Our team has been notified of the issue. We will fix it as soon as possible."

    def __init__(
        self,
        dev_message: str,
        user_message: str,
        agent_message: str | None,
        should_retry_later: bool = False,
        should_notify_team: bool = False,
    ) -> None:
        self.dev_message: str = dev_message
        self.user_message: str = user_message
        self.agent_message: str = agent_message or user_message
        self.should_retry_later: bool = should_retry_later
        self.should_notify_team: bool = should_notify_team
        # Use the appropriate message based on the mode

        match ErrorConfig.get_message_mode():
            case ErrorMessageMode.DEVELOPER:
                message = self.dev_message
            case ErrorMessageMode.USER:
                message = self.user_message
                if self.should_notify_team:
                    message += f" {self.NOTTE_TEAM_NOTIFIED_MESSAGE}"
                if self.should_retry_later:
                    message += f" {self.TRY_AGAIN_LATER_MESSAGE}"
            case ErrorMessageMode.AGENT:
                message = self.agent_message

        super().__init__(message)


class NotteTimeoutError(NotteBaseError):
    def __init__(self, message: str) -> None:
        super().__init__(dev_message=message, user_message=message, agent_message=message, should_retry_later=True)


class AccessibilityTreeMissingError(NotteBaseError):
    def __init__(self, message: str = "") -> None:
        error_message = f"Accessibility tree is missing. {message}"
        super().__init__(
            dev_message=error_message, user_message=error_message, agent_message=error_message, should_retry_later=True
        )


class UnexpectedBehaviorError(NotteBaseError):
    def __init__(self, message: str, advice: str) -> None:
        super().__init__(
            dev_message=f"Unexpected behavior: {message}. {advice}",
            user_message="Something unexpected happened.",
            agent_message=(
                "Something unexpected happened. There is likely an issue with this particular action or website."
            ),
            should_notify_team=True,
        )
