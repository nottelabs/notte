from notte_core.errors.base import NotteBaseError


class LLMnoOutputCompletionError(NotteBaseError):
    def __init__(self) -> None:
        super().__init__(
            dev_message="LLM completion failed. No content in response",
            user_message="Sorry, Notte failed to generate a valid response for your request this time.",
            agent_message="LLM completion failed to return a non-empty response. Hint: simply retry the same action.",
            should_retry_later=True,
        )


class LLMParsingError(NotteBaseError):
    def __init__(self, context: str) -> None:
        super().__init__(
            dev_message=f"Failed to parse LLM response. {context}",
            user_message="Sorry, Notte failed to generate a valid response for your request this time.",
            agent_message="Failed to parse LLM response. Hint: simply retry the same action.",
            should_retry_later=True,
        )


class ContextSizeTooLargeError(NotteBaseError):
    def __init__(self, size: int | None = None, max_size: int | None = None) -> None:
        super().__init__(
            dev_message=(
                f"The web page context size '{size or 'unknown'}' exceeds maximum allowed size of "
                f"'{max_size or 'unknown'}' of LLM provider. Please update processing pipeline to either "
                "reduce the context size for this particular webpage, use a LLM provider with a larger "
                "context size, or enable divide & conquer mode (currently in beta)."
            ),
            user_message=(
                "The web page content is currently too large to be processed by Notte. "
                "Our team is working on supporting this page."
            ),
            agent_message=(
                "The web page content is currently too large to be processed. There is nothing you can do this page is"
                " simply not available. You should terminate the current session or try another URL."
            ),
            should_retry_later=False,
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
