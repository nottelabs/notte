from pydantic import ValidationError

from notte.errors.base import NotteBaseError


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
        errors = []
        for err in error.errors():
            field = " -> ".join(str(loc) for loc in err["loc"])
            msg = err["msg"]
            errors.append(f"{field}: {msg}")

        return cls(param_name="model", details="\n".join(errors))


# def format_pydantic_validation_error(error: ValidationError) -> str:
#     """
#     Formats a Pydantic ValidationError into a clear, concise message.

#     Example output:
#     Validation Error:

#     Expected structure:
#     {
#         "key": str,      // required
#         "duration": int  // optional
#     }

#     Issues found:
#     Missing required fields:
#     - key in PressKeyAction
#     """

#     def format_error(err: dict[str, Any]) -> str:
#         loc = " -> ".join(str(item) for item in err["loc"])
#         if err["type"] == "missing":
#             return f"- {loc}"
#         return f"- {loc}: {err['msg']}"

#     # Get schema from the first error's context
#     # In Pydantic v2, we need to get the model info from the error context
#     first_error = error.errors()[0]
#     model_name = first_error.get("ctx", {}).get("class_name", "Unknown Model")

#     # Build field descriptions from the error context
#     field_descriptions: list[str] = []
#     seen_fields = set()

#     for err in error.errors():
#         ctx = err.get("ctx", {})
#         field_name = err["loc"][0] if err["loc"] else None

#         if field_name and field_name not in seen_fields:
#             seen_fields.add(field_name)
#             required = err["type"] == "missing"
#             field_type = ctx.get("expected_type", "any")
#             comment = "required" if required else "optional"
#             field_descriptions.append(f'    "{field_name}": {field_type},  // {comment}')

#     # Group errors by type
#     errors = error.errors()
#     missing_fields = [e for e in errors if e["type"] == "missing"]
#     invalid_fields = [e for e in errors if e["type"] != "missing"]

#     # Build the complete message
#     message_parts = [
#         f"Validation Error for {model_name}:",
#         "",
#         "Expected structure:",
#         "{",
#         "\n".join(sorted(field_descriptions)),
#         "}",
#         "",
#         "Issues found:",
#     ]

#     if missing_fields:
#         message_parts.extend(["Missing required fields:", *[format_error(err) for err in missing_fields]])

#     if invalid_fields:
#         if missing_fields:
#             message_parts.append("")
#         message_parts.extend(["Invalid fields:", *[format_error(err) for err in invalid_fields]])

#     return "\n".join(message_parts)
