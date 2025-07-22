from notte_core.common.config import LlmModel
from notte_core.errors.base import NotteBaseError


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
                "Please try another model or wait a few minutes. "
                f"Available models: {', '.join(LlmModel.valid())}"
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
