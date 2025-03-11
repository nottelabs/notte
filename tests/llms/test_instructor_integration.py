"""
Tests for the instructor integration module.
"""

import json
from typing import Sequence

from pydantic import BaseModel, Field

from notte.llms.instructor_integration import InstructorValidator, validate_structured_output


class TestModel(BaseModel):
    """Test model for validation."""

    name: str
    age: int = Field(gt=0)
    email: str | None = None


def test_validate_json_success():
    """Test successful JSON validation."""
    validator = InstructorValidator(TestModel)
    valid_json = '{"name": "John", "age": 30, "email": "john@example.com"}'

    result, errors = validator.validate_json(valid_json)

    assert result is not None
    assert isinstance(result, TestModel)
    assert result.name == "John"
    assert result.age == 30
    assert result.email == "john@example.com"
    assert not errors


def test_validate_json_with_minimal_data():
    """Test validation with minimal required fields."""
    validator = InstructorValidator(TestModel)
    minimal_json = '{"name": "John", "age": 25}'

    result, errors = validator.validate_json(minimal_json)

    assert result is not None
    assert isinstance(result, TestModel)
    assert result.name == "John"
    assert result.age == 25
    assert result.email is None
    assert not errors


def test_validate_json_missing_required():
    """Test validation with missing required fields."""
    validator = InstructorValidator(TestModel)
    invalid_json = '{"age": 30}'

    result, errors = validator.validate_json(invalid_json)

    assert result is None
    assert len(errors) == 1
    assert "name" in errors[0]
    assert "Field required" in errors[0]


def test_validate_json_invalid_type():
    """Test validation with invalid field types."""
    validator = InstructorValidator(TestModel)
    invalid_json = '{"name": "John", "age": "thirty"}'

    result, errors = validator.validate_json(invalid_json)

    assert result is None
    assert len(errors) == 1
    assert "age" in errors[0]
    assert "Input should be a valid integer" in errors[0]


def test_validate_json_invalid_constraint():
    """Test validation with invalid field constraints."""
    validator = InstructorValidator(TestModel)
    invalid_json = '{"name": "John", "age": 0}'

    result, errors = validator.validate_json(invalid_json)

    assert result is None
    assert len(errors) == 1
    assert "age" in errors[0]
    assert "greater than" in errors[0]


def test_validate_json_invalid_json_syntax():
    """Test validation with invalid JSON syntax."""
    validator = InstructorValidator(TestModel)
    invalid_json = '{"name": "John", age: 30}'  # Missing quotes around age

    result, errors = validator.validate_json(invalid_json)

    assert result is None
    assert len(errors) > 0


def test_generate_error_prompt():
    """Test error prompt generation."""
    validator = InstructorValidator(TestModel)
    errors = ["name: Field required", "age: Input should be a valid integer"]
    original_json = '{"age": "thirty"}'

    prompt = validator.generate_error_prompt(errors, original_json)

    assert "validation errors" in prompt
    assert "1. name: Field required" in prompt
    assert "2. age: Input should be a valid integer" in prompt
    assert "schema" in prompt
    assert "original JSON" in prompt
    assert original_json in prompt


def test_validate_structured_output_helper():
    """Test the helper function for structured output validation."""
    valid_json = '{"name": "John", "age": 30}'

    result, errors = validate_structured_output(valid_json, TestModel)

    assert result is not None
    assert isinstance(result, TestModel)
    assert result.name == "John"
    assert result.age == 30
    assert not errors


def test_validate_structured_output_helper_invalid():
    """Test the helper function with invalid input."""
    invalid_json = '{"name": "John"}'  # Missing required age field

    result, errors = validate_structured_output(invalid_json, TestModel)

    assert result is None
    assert len(errors) == 1
    assert "age" in errors[0]
    assert "Field required" in errors[0]


class TestAction(BaseModel):
    """Test action model for validation."""

    name: str
    parameters: dict[str, str] = Field(default_factory=dict)


class TestOutput(BaseModel):
    """Test output model for validation."""

    actions: Sequence[TestAction] = Field(min_length=1)
    state: dict[str, str]


def test_validate_complex_json_success():
    """Test successful validation of complex JSON."""
    validator = InstructorValidator(TestOutput)

    valid_json = json.dumps(
        {"actions": [{"name": "test_action", "parameters": {"param1": "value1"}}], "state": {"key": "value"}}
    )

    result, errors = validator.validate_json(valid_json)

    assert result is not None
    assert len(errors) == 0
    assert len(result.actions) == 1
    assert result.actions[0].name == "test_action"
    assert result.state == {"key": "value"}


def test_validate_complex_json_failure():
    """Test validation failure with empty actions list."""
    validator = InstructorValidator(TestOutput)

    invalid_json = json.dumps(
        {
            "actions": [],  # Empty list, violates min_length=1
            "state": {"key": "value"},
        }
    )

    result, errors = validator.validate_json(invalid_json)

    assert result is None
    assert len(errors) > 0
    assert any("actions" in error for error in errors)


def test_complex_error_prompt():
    """Test generation of error prompt for complex model."""
    validator = InstructorValidator(TestOutput)

    errors = ["actions: List should have at least 1 item after validation"]
    original_json = '{"actions": [], "state": {"key": "value"}}'

    prompt = validator.generate_error_prompt(errors, original_json)

    assert "actions: List should have at least 1 item after validation" in prompt
    assert original_json in prompt
    assert "schema" in prompt.lower()
