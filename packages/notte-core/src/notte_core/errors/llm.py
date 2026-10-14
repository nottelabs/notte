from notte_core.errors.base import NotteBaseError


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
