import contextlib
from enum import Enum
from typing import ClassVar, Literal

# Base errors and message modes


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


# Actions errors


class ActionError(NotteBaseError):
    """Base class for Action related errors."""

    pass


class EvaluateJsResultLimitError(ActionError):
    def __init__(self, max_bytes: int, reason: str) -> None:
        message = (
            f"JavaScript result exceeds conversion limits ({reason}; output limit {max_bytes} bytes). "
            "Return fewer fields, a summary, or retrieve the result in smaller batches."
        )
        super().__init__(dev_message=message, user_message=message, agent_message=message)


class ActionExecutionError(ActionError):
    def __init__(self, action_id: str, url: str, reason: str | None = None) -> None:
        super().__init__(
            dev_message=f"Failed to execute action: {action_id} on {url}. Reason: {reason or 'unknown'}",
            user_message="Sorry, this action cannot be executed at the moment.",
            agent_message=(
                f"Failed to execute action: {action_id} on {url}. Reason: {reason or 'unknown'}. "
                "Hint: check if the action is valid and try again. Otherwise, try another action."
            ),
            should_retry_later=True,
            should_notify_team=True,
        )


class EvaluateJsNoDataError(ActionError):
    def __init__(self) -> None:
        message = "evaluate_js reported success but returned no data"
        super().__init__(
            dev_message=message,
            user_message=f"{message}.",
            agent_message=message,
            should_notify_team=True,
        )


class FetchResponseDecodeError(ActionError):
    def __init__(self, reason: str) -> None:
        message = f"fetch script returned an unreadable response envelope: {reason}"
        super().__init__(
            dev_message=message,
            user_message=f"{message}.",
            agent_message=message,
            should_notify_team=True,
        )


class InvalidActionError(ActionError):
    def __init__(self, action_id: str, reason: str) -> None:
        super().__init__(
            dev_message=f"Action with id '{action_id}' is invalid: {reason}.",
            user_message=f"Action with id '{action_id}' is invalid. Please provide a valid action and try again.",
            agent_message=(
                f"Action with id '{action_id}' is invalid. Hint: provide a valid action and try again. "
                "Otherwise, try another action."
            ),
        )


class VaultCredentialError(ActionError):
    """A vault credential could not be filled, so its placeholder was not typed into the page."""

    def __init__(self, reason: str) -> None:
        msg = f"Could not fill a vault credential: {reason.rstrip('.')}. The credential placeholder was not typed into the page."
        super().__init__(dev_message=msg, user_message=msg, agent_message=msg)


class NoCredentialsFoundError(ActionError):
    def __init__(self, url: str) -> None:
        msg = (
            f"No credentials found in the vault for url={url}. Please add valid credentials in the vault and try again."
        )
        super().__init__(
            dev_message=msg,
            user_message=msg,
            agent_message=msg,
        )


# Llm errors


class LLMParsingError(NotteBaseError):
    def __init__(self, context: str) -> None:
        super().__init__(
            dev_message=f"Failed to parse LLM response. {context}",
            user_message="Sorry, Notte failed to generate a valid response for your request this time.",
            agent_message="Failed to parse LLM response. Hint: simply retry the same action.",
            should_retry_later=True,
        )


class InvalidPromptTemplateError(NotteBaseError):
    def __init__(self, prompt_id: str, message: str) -> None:
        super().__init__(
            dev_message=(
                f"Invalid prompt template: {prompt_id}. {message}. This should not happen in production environment."
            ),
            user_message="Sorry, Notte failed to generate a valid response for your request this time.",
            should_retry_later=False,
            # should not happen in production environment
            agent_message=None,
        )


class LLmModelOverloadedError(NotteBaseError):
    def __init__(self, model_name: str) -> None:
        super().__init__(
            dev_message=f"Model {model_name} is overloaded. Please try another model or try again later.",
            user_message=f"Model {model_name} is overloaded. Please try another model or try again later.",
            agent_message=f"Model {model_name} is overloaded. Please try another model or try again later.",
            should_retry_later=True,
        )


# Processing errors


class SnapshotProcessingError(NotteBaseError):
    """
    Error raised when there is an issue processing a snapshot.
    All of these issues should, in theory, not occur but, in practice,
    since Notte is still in development, they are likely to happen.

    Most of them should be fixed by updating the preprocessing pipeline.
    """

    def __init__(self, url: str | None, dev_message: str) -> None:
        url_str = f": {url}" if url else ""
        super().__init__(
            dev_message=dev_message,
            user_message=f"Sorry, Notte is not yet able to process this website{url_str}.",
            agent_message="Sorry, this action is not yet supported. Hint: try another action.",
            should_notify_team=True,
        )


class InvalidInternalCheckError(SnapshotProcessingError):
    """
    Multiple internal checks are performed when the snapshot is processed.
    This error is raised when one of the internal checks fails.

    To fix this error, developers should:
    - Undersand with the internal check failed
    - Decide wether the internal check is simply not relevant for the given snapshot
    - Or if custom processing need to be handled by the developer for the given snapshot
    """

    def __init__(self, url: str | None, check: str, dev_advice: str) -> None:
        super().__init__(
            dev_message=f"Internal check '{check}' failed during snapshot processing. Advice to resolve: {dev_advice}",
            url=url,
        )


class InvalidPlaceholderError(NotteBaseError):
    def __init__(self, placeholder: str) -> None:
        dev_message = f"The placeholder {placeholder} is not handled by your current vault."
        agent_message = f"Could not perform action with value {placeholder}. Try picking a different value"
        user_message = "Unexpected error while requesting credentials from vault"

        super().__init__(
            agent_message=agent_message,
            user_message=user_message,
            dev_message=dev_message,
        )


class ScrapeFailedError(NotteBaseError):
    def __init__(self, error_message: str) -> None:
        super().__init__(
            dev_message=f"Structured data extraction failed: {error_message}",
            user_message=f"Failed to extract structured data: {error_message}",
            agent_message=f"Structured data extraction failed: {error_message}. Hint: verify the page contains the expected data or adjust your instructions.",
            should_retry_later=True,
        )


# Provider errors


class LLMProviderError(NotteBaseError):
    """Base class for LLM provider related errors."""

    pass


class ModelNotFoundError(LLMProviderError):
    def __init__(self, model: str) -> None:
        super().__init__(
            dev_message=f"Model {model} not found",
            user_message=f"The model '{model}' is not available. Please try a different model.",
            agent_message=None,
            should_retry_later=False,
        )


class RateLimitError(LLMProviderError):
    def __init__(self, provider: str) -> None:
        super().__init__(
            dev_message=f"Rate limit exceeded for provider {provider}",
            user_message=(
                "Service is temporarily unavailable due to high traffic. "
                "Please try another model or wait a few minutes."
            ),
            should_retry_later=True,
            agent_message="Rate limit exceeded. Cannot proceed with the request. Please wait 30s before retrying.",
        )


class InvalidAPIKeyError(LLMProviderError):
    def __init__(self, provider: str) -> None:
        super().__init__(
            dev_message=f"Invalid API key for {provider}",
            user_message="Authentication failed. Please check your credentials or upgrade your plan.",
            should_retry_later=False,
            agent_message="Invalid API key. Hint: terminate the current session with a failure status immediately.",
        )


class ContextWindowExceededError(LLMProviderError):
    def __init__(self, provider: str, current_size: int | None = None, max_size: int | None = None) -> None:
        size_info = ""
        if current_size is not None and max_size is not None:
            size_info = f" Current size: {current_size}, Maximum size: {max_size}."
        super().__init__(
            dev_message=f"Context window exceeded for provider {provider}.{size_info}",
            user_message="The input is too long for this model to process. Please reduce the length of your input.",
            should_retry_later=False,
            agent_message=(
                "Context window exceeded, there is too much information to process. Go back or try another URL."
            ),
        )


class InsufficentCreditsError(LLMProviderError):
    def __init__(self) -> None:
        super().__init__(
            dev_message="Insufficient credits for LLM provider. Please check your account and top up your credits.",
            user_message="Sorry, Notte failed to generate a valid response for your request this time.",
            should_retry_later=True,
            agent_message=(
                "Insufficient credits. Hint: terminate the current session with a failure status immediately."
            ),
        )


class ModelDoesNotSupportImageError(LLMProviderError):
    def __init__(self, model: str) -> None:
        super().__init__(
            dev_message=(
                f"Model {model} does not support vision / image as input. "
                "Please set `use_vision=False` in the `Agent` constructor."
                " or use a model that supports vision (e.g. openai/gpt-4o)"
            ),
            user_message="The model does not support images.",
            agent_message=None,
        )


class MissingAPIKeyForModel(LLMProviderError):
    def __init__(self, model: str) -> None:
        super().__init__(
            dev_message=(
                f"The llm {model} does not have an associated API key"
                "If you think this is wrong, try to set both perception"
                "and reasoning models"
            ),
            user_message="The selected model does not have an associated API key",
            agent_message=None,
        )


class InvalidJsonResponseForStructuredOutput(LLMProviderError):
    def __init__(self, model: str, error_msg: str) -> None:
        super().__init__(
            dev_message=f"Invalid JSON response for structured output for model {model}. Error message: {error_msg}",
            user_message=f"The model returned an invalid JSON response for structured output. Error message: {error_msg}",
            agent_message=None,
        )
