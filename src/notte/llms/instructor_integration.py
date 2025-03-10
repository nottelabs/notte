"""
Instructor integration for enhanced structured output handling.

This module provides integration with the Instructor library for better structured output
validation and handling. It focuses on validation and error reporting, leaving retry
logic to the caller.
"""

from typing import Generic, TypeVar

from pydantic import BaseModel, ValidationError
from typing_extensions import final

# Type variable for response format
T = TypeVar("T", bound=BaseModel)


@final
class InstructorValidator(Generic[T]):
    """
    Validator for structured outputs using Instructor-like validation patterns.

    This class provides validation and error reporting for structured outputs
    from LLMs, similar to how Instructor works but without the direct dependency.
    """

    response_model: type[T]

    def __init__(self, response_model: type[T]):
        """
        Initialize the validator.

        Args:
            response_model: The Pydantic model to validate against
        """
        self.response_model = response_model

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


def validate_structured_output(json_str: str, response_model: type[T]) -> tuple[T | None, list[str]]:
    """
    Validate structured output and return validation results.

    Args:
        json_str: JSON string to validate
        response_model: Pydantic model to validate against

    Returns:
        Tuple of (validated model or None, list of error messages)
    """
    validator = InstructorValidator(response_model=response_model)
    return validator.validate_json(json_str)
