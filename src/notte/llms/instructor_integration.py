"""
Instructor integration for enhanced structured output handling.

This module provides integration with the Instructor library for better structured output
validation and handling. It includes fallback mechanisms to handle validation errors and
retry strategies to improve the reliability of LLM outputs.
"""

from collections.abc import Sequence
from typing import Any, Callable, Generic, TypeVar

from loguru import logger
from pydantic import BaseModel, ValidationError
from typing_extensions import final

# Type variable for response format
T = TypeVar("T", bound=BaseModel)


@final
class InstructorValidator(Generic[T]):
    """
    Validator for structured outputs using Instructor-like validation patterns.

    This class provides validation and retry mechanisms for structured outputs
    from LLMs, similar to how Instructor works but without the direct dependency.
    """

    response_model: type[T]
    max_retries: int
    llm_completion_fn: Callable[[Sequence[dict[str, Any]], dict[str, Any]], str] | None

    def __init__(
        self,
        response_model: type[T],
        max_retries: int = 3,
        llm_completion_fn: Callable[[Sequence[dict[str, Any]], dict[str, Any]], str] | None = None,
    ):
        """
        Initialize the validator.

        Args:
            response_model: The Pydantic model to validate against
            max_retries: Maximum number of retries for validation
            llm_completion_fn: Function to call for LLM completions during retries
        """
        self.response_model = response_model
        self.max_retries = max_retries
        self.llm_completion_fn = llm_completion_fn

    def validate_json(self, json_str: str) -> tuple[T | None, list[str]]:
        """
        Validate JSON against the response model.

        Args:
            json_str: JSON string to validate

        Returns:
            Tuple of (validated model or None, list of error messages)
        """
        errors: list[str] = []
        try:
            # Try to validate the JSON against the response model
            result = self.response_model.model_validate_json(json_str)
            return result, errors
        except ValidationError as e:
            # Extract error messages
            for error in e.errors():
                loc = " -> ".join(str(loc_part) for loc_part in error["loc"])
                msg = f"{loc}: {error['msg']}"
                errors.append(msg)
            return None, errors

    def generate_error_prompt(self, errors: list[str], original_json: str) -> str:
        """
        Generate a prompt to fix validation errors.

        Args:
            errors: List of validation error messages
            original_json: The original JSON that failed validation

        Returns:
            A prompt to send to the LLM to fix the errors
        """
        schema = self.response_model.model_json_schema()

        prompt = "The JSON you provided has validation errors. Please fix the following issues:\n\n"

        for i, error in enumerate(errors, 1):
            prompt += f"{i}. {error}\n"

        prompt += "\nHere's the schema you need to follow:\n"
        prompt += f"{schema}\n\n"
        prompt += "Here's your original JSON with errors:\n"
        prompt += f"{original_json}\n\n"
        prompt += "Please provide a corrected JSON that follows the schema and fixes all the errors:"

        return prompt

    def validate_with_retries(self, json_str: str, messages: Sequence[dict[str, Any]] | None = None) -> T:
        """
        Validate JSON with retries using the LLM to fix errors.

        Args:
            json_str: JSON string to validate
            messages: Messages to use for LLM completion if needed

        Returns:
            Validated model

        Raises:
            ValueError: If validation fails after max retries
        """
        current_json = json_str
        retries = 0

        while retries <= self.max_retries:
            result, errors = self.validate_json(current_json)

            if result is not None:
                return result

            # Only stop retrying if we've reached max retries or don't have an LLM function
            if retries == self.max_retries or not self.llm_completion_fn:
                error_details = "\n".join(errors)
                raise ValueError(f"Failed to validate JSON after {retries} retries. Errors:\n{error_details}")

            # Generate error prompt and retry with LLM
            error_prompt = self.generate_error_prompt(errors, current_json)

            # Initialize messages if None
            retry_messages_list = (
                list(messages) if messages else [{"role": "user", "content": "Fix the following JSON:"}]
            )

            # Add error prompt to messages
            if retry_messages_list and retry_messages_list[-1]["role"] == "user":
                # Update the last user message
                retry_messages_list[-1]["content"] = error_prompt
            else:
                # Add a new user message
                retry_messages_list.append({"role": "user", "content": error_prompt})

            try:
                # Call LLM to fix errors
                current_json = self.llm_completion_fn(retry_messages_list, {"type": "json_object"})
                logger.info(f"Retry {retries + 1}: LLM provided fixed JSON")
            except Exception as e:
                logger.error(f"Error during LLM retry: {e}")
                raise ValueError(f"Failed to validate JSON: {errors}")

            retries += 1

        # This should not be reached due to the check in the loop
        raise ValueError("Unexpected error in validation retry loop")


def validate_structured_output(
    json_str: str,
    response_model: type[T],
    max_retries: int = 3,
    llm_completion_fn: Callable[[Sequence[dict[str, Any]], dict[str, Any]], str] | None = None,
    messages: Sequence[dict[str, Any]] | None = None,
) -> T:
    """
    Validate structured output with retries.

    Args:
        json_str: JSON string to validate
        response_model: Pydantic model to validate against
        max_retries: Maximum number of retries
        llm_completion_fn: Function to call for LLM completions during retries
        messages: Messages to use for LLM completion if needed

    Returns:
        Validated model

    Raises:
        ValueError: If validation fails after max retries
    """
    validator = InstructorValidator(
        response_model=response_model,
        max_retries=max_retries,
        llm_completion_fn=llm_completion_fn,
    )

    return validator.validate_with_retries(json_str, messages)
