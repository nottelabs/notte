"""
Tests for the instructor integration module.
"""

import json
from collections.abc import Sequence

import pytest
from pydantic import BaseModel, Field

from notte.llms.instructor_integration import InstructorValidator, validate_structured_output


class TestAction(BaseModel):
    """Test action model for validation."""

    name: str
    parameters: dict[str, str] = Field(default_factory=dict)


class TestOutput(BaseModel):
    """Test output model for validation."""

    actions: Sequence[TestAction] = Field(min_length=1)
    state: dict[str, str]


def test_validate_json_success():
    """Test successful validation of JSON."""
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


def test_validate_json_failure():
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


def test_generate_error_prompt():
    """Test generation of error prompt."""
    validator = InstructorValidator(TestOutput)

    errors = ["actions: List should have at least 1 item after validation"]
    original_json = '{"actions": [], "state": {"key": "value"}}'

    prompt = validator.generate_error_prompt(errors, original_json)

    assert "actions: List should have at least 1 item after validation" in prompt
    assert original_json in prompt
    assert "schema" in prompt.lower()


def test_validate_with_retries_success():
    """Test successful validation with retries."""

    # Mock LLM completion function that returns valid JSON on first call
    def mock_llm_completion(messages, fmt):
        return json.dumps(
            {"actions": [{"name": "test_action", "parameters": {"param1": "value1"}}], "state": {"key": "value"}}
        )

    validator = InstructorValidator(TestOutput, max_retries=1, llm_completion_fn=mock_llm_completion)

    # Start with invalid JSON
    invalid_json = json.dumps(
        {
            "actions": [],  # Empty list, violates min_length=1
            "state": {"key": "value"},
        }
    )

    # Should succeed after one retry
    result = validator.validate_with_retries(invalid_json, messages=[])

    assert result is not None
    assert len(result.actions) == 1
    assert result.actions[0].name == "test_action"


def test_validate_with_retries_failure():
    """Test validation failure after max retries."""

    # Mock LLM completion function that always returns invalid JSON
    def mock_llm_completion(messages, fmt):
        return json.dumps(
            {
                "actions": [],  # Still invalid
                "state": {"key": "value"},
            }
        )

    validator = InstructorValidator(TestOutput, max_retries=2, llm_completion_fn=mock_llm_completion)

    # Start with invalid JSON
    invalid_json = json.dumps(
        {
            "actions": [],  # Empty list, violates min_length=1
            "state": {"key": "value"},
        }
    )

    # Should fail after max retries
    with pytest.raises(ValueError) as excinfo:
        validator.validate_with_retries(invalid_json, messages=[])

    assert "Failed to validate JSON after" in str(excinfo.value)


def test_validate_structured_output():
    """Test the validate_structured_output helper function."""

    # Mock LLM completion function that returns valid JSON
    def mock_llm_completion(messages, fmt):
        return json.dumps(
            {"actions": [{"name": "fixed_action", "parameters": {"param1": "value1"}}], "state": {"key": "value"}}
        )

    # Start with invalid JSON
    invalid_json = json.dumps(
        {
            "actions": [],  # Empty list, violates min_length=1
            "state": {"key": "value"},
        }
    )

    # Should succeed with the helper function
    result = validate_structured_output(
        json_str=invalid_json,
        response_model=TestOutput,
        max_retries=1,
        llm_completion_fn=mock_llm_completion,
        messages=[],
    )

    assert result is not None
    assert len(result.actions) == 1
    assert result.actions[0].name == "fixed_action"
