from pydantic import ValidationError

from notte_core.errors.base import NotteBaseError


class PydanticValidationError(NotteBaseError):
    """Base class for input/parameter validation errors."""

    def __init__(self, param_name: str, details: str) -> None:
        super().__init__(
            dev_message=f"Invalid parameter '{param_name}': {details}",
            user_message=f"Invalid input provided for '{param_name}'",
            should_retry_later=False,
            # agent message not relevant here
            agent_message="Invalid input provided. Please check the input and try again.",
        )


class ModelValidationError(PydanticValidationError):
    """Handles Pydantic model validation errors in a cleaner way."""

    @classmethod
    def from_pydantic_error(cls, error: ValidationError) -> "ModelValidationError":
        # Convert Pydantic's error format into a more readable structure
        errors: list[str] = []
        for err in error.errors():
            field = " -> ".join(str(loc) for loc in err["loc"])
            msg = err["msg"]
            errors.append(f"{field}: {msg}")

        return cls(param_name="model", details="\n".join(errors))
