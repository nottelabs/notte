from notte.errors.base import NotteBaseError


class LLMProviderError(NotteBaseError):
    """Base class for LLM provider related errors."""

    pass


class RateLimitError(LLMProviderError):
    def __init__(self, provider: str) -> None:
        super().__init__(
            dev_message=f"Rate limit exceeded for provider {provider}",
            user_message="Service is temporarily unavailable due to high traffic.",
            should_retry_later=True,
        )


class InvalidAPIKeyError(LLMProviderError):
    def __init__(self, provider: str) -> None:
        super().__init__(
            dev_message=f"Invalid API key for {provider}",
            user_message="Authentication failed. Please check your credentials or upgrade your plan.",
            should_retry_later=False,
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
        )


class InsufficentCreditsError(LLMProviderError):
    def __init__(self) -> None:
        super().__init__(
            dev_message="Insufficient credits for LLM provider. Please check your account and top up your credits.",
            user_message="Sorry, Notte failed to generate a valid response for your request this time.",
            should_retry_later=True,
        )
