import contextlib
import re
from enum import Enum
from typing import ClassVar, Literal
from urllib.parse import urlparse

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


class NoCredentialsFoundError(ActionError):
    """Raised when a credential placeholder is used on a site the vault holds no credentials for.

    The action fails and nothing is typed into the page.
    """

    def __init__(self, url: str) -> None:
        # Only name the site: the full URL can carry tokens in its path or query
        site = urlparse(url).hostname or "the current page"
        msg = (
            f"No vault credentials for {site}, so the credential placeholder was not filled. "
            "Credentials for this site must be added to the vault before they can be used."
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


class CredentialReplacementError(NotteBaseError):
    """Base class for errors raised while replacing credential placeholders with vault values.

    The action carrying the placeholder must fail instead of typing the literal placeholder into the page.
    Messages must never include credential values: only refer to the credential by field type.
    """

    pass


class InvalidPlaceholderError(CredentialReplacementError):
    """Raised when an action value contains a credential placeholder but is not exactly a known placeholder."""

    def __init__(self, field_name: str | None = None) -> None:
        field_str = f" for field {field_name!r}" if field_name else ""
        dev_message = (
            f"The credential value{field_str} is not an exact vault placeholder. "
            "Use one of the vault placeholders as the whole value, without any other text."
        )
        agent_message = (
            f"Could not fill the credential{field_str}: the value must be exactly one of the vault placeholders, "
            "without any other text. Retry with the exact placeholder."
        )
        user_message = "Unexpected error while requesting credentials from vault"

        super().__init__(
            agent_message=agent_message,
            user_message=user_message,
            dev_message=dev_message,
        )


class MissingCredentialFieldError(CredentialReplacementError):
    """Raised when the vault holds credentials for the page, but not the requested field."""

    def __init__(self, cred_key: str) -> None:
        message = f"No credential of type {cred_key!r} found in the vault."
        super().__init__(
            dev_message=f"{message} Add it to the vault and try again.",
            user_message=message,
            agent_message=f"{message} Do not use the {cred_key!r} placeholder: try another login method or field.",
        )


class VaultLookupError(CredentialReplacementError):
    """Raised when the vault could not be queried for a credential."""

    def __init__(self, cred_key: str, error_type: str) -> None:
        message = f"Could not retrieve credential of type {cred_key!r} from the vault ({error_type})."
        super().__init__(
            dev_message=message,
            user_message=message,
            agent_message=message,
            should_retry_later=True,
        )


class CredentialFieldValidationError(CredentialReplacementError):
    """Raised when a credential placeholder targets an element that is not a valid input for that
    credential (e.g. a password placeholder targeted at a <label> instead of the password input).
    Without this error the literal placeholder string would be typed into the page."""

    def __init__(self, placeholder: str, cred_key: str, element_type: str | None, outer_html: str | None) -> None:
        # Only report the tag name: the element's HTML can carry sensitive attribute values
        tag_match = re.match(r"\s*<\s*([a-zA-Z][a-zA-Z0-9-]*)", outer_html or "")
        tag_name = tag_match.group(1).lower() if tag_match else None
        dev_message = (
            f"Credential placeholder {placeholder!r} for field {cred_key!r} targeted an element that is not a "
            f"valid {cred_key!r} input (tag={tag_name!r}, type={element_type!r}). "
            "Common cause: the action targeted a wrapper (e.g. <label>) instead of the actual <input>. "
            "Target the input element directly."
        )
        agent_message = (
            f"Could not fill credential {cred_key!r}: the targeted element is not a valid {cred_key!r} input. "
            "Target the actual input field and retry."
        )
        user_message = "Credential placeholder used on an element that is not a valid target for that field."
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


class ContentFilterError(LLMProviderError):
    """The provider refused the request on content-policy grounds (not an authentication failure)."""

    def __init__(self, model: str, detail: str | None = None) -> None:
        reason = f": {detail}" if detail else ""
        super().__init__(
            dev_message=f"The provider of {model} refused the request on content-policy grounds{reason}",
            user_message=f"The LLM provider of {model} refused the request on content-policy grounds.",
            agent_message=None,
            should_retry_later=False,
        )
        self.model: str = model


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
    def __init__(self, model: str, api_key_variables: str = "NOTTE_LLM_API_KEY or OPENROUTER_API_KEY") -> None:
        super().__init__(
            dev_message=(f"The LLM {model} does not have an associated API key. Set {api_key_variables}."),
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


class UnsupportedResponseSchemaError(LLMProviderError):
    def __init__(self, model: str, error_msg: str) -> None:
        super().__init__(
            dev_message=f"Provider for model {model} rejected the structured output schema. Error message: {error_msg}",
            user_message="The model provider does not support this structured output schema.",
            agent_message=None,
        )
