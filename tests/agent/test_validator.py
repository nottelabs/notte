import json
from typing import Any

import pytest
from notte_agent.common.validator import CompletionValidator
from notte_core.actions import CompletionAction
from notte_core.utils.pydantic_schema import convert_response_format_to_pydantic_model
from pydantic import BaseModel, Field

import notte


class Product(BaseModel):
    name: str
    price: int = Field(le=5, ge=0)


class ProductResponse(BaseModel):
    products: list[dict[str, Product]] = Field(min_length=2, max_length=3)
    total_price: str = Field(
        default="",
        description="Final amount to be paid including all components",
    )


@pytest.fixture
def json_schema() -> dict[Any, Any]:
    return ProductResponse.model_json_schema()


@pytest.fixture
def output_in_constraints() -> str:
    return json.dumps(
        {
            "products": [
                {"a": {"name": "a", "price": 5}},
                {"b": {"name": "bprod", "price": 3}},
            ],
            "total_price": "5",
        }
    )


@pytest.fixture
def output_wrong_type() -> str:
    return json.dumps(
        {
            "products": [
                {"a": {"name": "a", "price": 5}},
                {"b": {"name": "bprod", "price": -1}},
            ],
            "total_price": 5,
        }
    )


@pytest.fixture
def output_length() -> str:
    return json.dumps(
        {
            "products": [
                {"a": {"name": "a", "price": 5}},
            ],
            "total_price": 5,
        }
    )


@pytest.fixture
def output_ge() -> str:
    return json.dumps(
        {
            "products": [
                {"a": {"name": "a", "price": 5}},
                {"b": {"name": "bprod", "price": -1}},
            ],
            "total_price": -1,
        }
    )


def test_valid(output_in_constraints: str, json_schema: dict[Any, Any]):
    response_format = convert_response_format_to_pydantic_model(json_schema)
    assert response_format is not None
    valid = CompletionValidator.validate_response_format(
        CompletionAction(success=True, answer=output_in_constraints), response_format
    )
    assert valid.is_valid


def test_wrong_type(output_wrong_type: str, json_schema: dict[Any, Any]):
    response_format = convert_response_format_to_pydantic_model(json_schema)
    assert response_format is not None
    valid = CompletionValidator.validate_response_format(
        CompletionAction(success=True, answer=output_wrong_type), response_format
    )
    assert not valid.is_valid


def test_length(output_length: str, json_schema: dict[Any, Any]):
    response_format = convert_response_format_to_pydantic_model(json_schema)
    assert response_format is not None
    valid = CompletionValidator.validate_response_format(
        CompletionAction(success=True, answer=output_length), response_format
    )
    assert not valid.is_valid


def test_ge(output_ge: str, json_schema: dict[Any, Any]):
    response_format = convert_response_format_to_pydantic_model(json_schema)
    assert response_format is not None
    valid = CompletionValidator.validate_response_format(
        CompletionAction(success=True, answer=output_ge), response_format
    )
    assert not valid.is_valid


def test_agent_with_schema():
    with notte.Session() as session:
        agent = notte.Agent(session=session, max_steps=5)
        valid = agent.run(
            task='CRITICAL: dont do anything, return a successfull completion action directly with output {"name": "my name", "price": -3}. You are allowed to shift the price if it fails.',
            response_format=Product,
        )
    assert valid.success, f"Failed to validate output: {valid.answer}"
    _ = Product.model_validate_json(valid.answer)


def test_execution_result_includes_url():
    """Test that ExecutionResult now includes URL context for actions."""
    from notte_core.actions import ClickAction
    from notte_core.browser.observation import ExecutionResult, TimedSpan

    span = TimedSpan.empty()

    # Test with URL
    result_with_url = ExecutionResult(
        action=ClickAction(id="L1"),
        success=True,
        message="Clicked on element",
        url="https://example.com",
        started_at=span.started_at,
        ended_at=span.ended_at,
    )
    assert result_with_url.url == "https://example.com"

    # Test without URL (backwards compatible)
    result_without_url = ExecutionResult(
        action=ClickAction(id="L1"),
        success=True,
        message="Clicked on element",
        started_at=span.started_at,
        ended_at=span.ended_at,
    )
    assert result_without_url.url is None


def test_perceive_action_result_includes_url():
    """Test that perceive_action_result includes URL in the output string."""
    from notte_agent.falco.perception import FalcoPerception
    from notte_core.actions import ClickAction
    from notte_core.browser.observation import ExecutionResult, TimedSpan

    perception = FalcoPerception()
    span = TimedSpan.empty()

    # Test success with URL
    result_success = ExecutionResult(
        action=ClickAction(id="L1"),
        success=True,
        message="Clicked on element with text label: Learn more",
        url="https://example.com",
        started_at=span.started_at,
        ended_at=span.ended_at,
    )
    output_success = perception.perceive_action_result(result_success)
    assert "(on https://example.com)" in output_success
    assert "succeeded" in output_success

    # Test failure with URL
    result_failure = ExecutionResult(
        action=ClickAction(id="L1"),
        success=False,
        message="Element not found",
        url="https://example.com/page",
        started_at=span.started_at,
        ended_at=span.ended_at,
    )
    output_failure = perception.perceive_action_result(result_failure)
    assert "(on https://example.com/page)" in output_failure
    assert "failed" in output_failure

    # Test without URL (backwards compatible)
    result_no_url = ExecutionResult(
        action=ClickAction(id="L1"),
        success=True,
        message="Clicked",
        started_at=span.started_at,
        ended_at=span.ended_at,
    )
    output_no_url = perception.perceive_action_result(result_no_url)
    assert "(on " not in output_no_url  # No URL prefix should appear


def test_validator_system_prompt_has_multipage_context():
    """Test that the validator system prompt includes multi-page context explanation."""
    from notte_agent.common.validator import system_rules

    # Check that the system prompt contains the multi-page context explanation
    assert "IMPORTANT:" in system_rules
    assert "multiple pages" in system_rules.lower()
    assert "Element IDs" in system_rules or "element ids" in system_rules.lower()
    assert "reset" in system_rules.lower()


def test_validator_receives_url_in_action_history():
    """
    Integration test: Verify that when the validator receives action history,
    each action includes the URL where it was executed.

    This tests the fix for the bug where the validator would incorrectly reject
    valid completions because actions executed on previous pages appeared to
    reference non-existent elements on the current page.
    """
    from unittest.mock import MagicMock

    from notte_agent.common.validator import CompletionValidator
    from notte_agent.falco.perception import FalcoPerception
    from notte_core.actions import ClickAction, CompletionAction
    from notte_core.browser.observation import ExecutionResult, Observation, TimedSpan, TrajectoryProgress
    from notte_core.trajectory import Trajectory

    # Create a mock trajectory that simulates:
    # 1. Click on "Learn more" link on example.com
    # 2. Page navigates to iana.org
    span = TimedSpan.empty()

    # Simulate click action that was executed on example.com
    click_result = ExecutionResult(
        action=ClickAction(id="L1"),
        success=True,
        message="Clicked on element with text label: Learn more",
        url="https://example.com",  # KEY: This URL shows where the action was executed
        started_at=span.started_at,
        ended_at=span.ended_at,
    )

    trajectory = Trajectory()

    import asyncio

    asyncio.run(trajectory.append(click_result))

    # Create perception and verify it includes URL in output
    perception = FalcoPerception()
    action_result_str = perception.perceive_action_result(click_result)

    # Verify URL is included in the action result string
    assert "(on https://example.com)" in action_result_str, (
        f"URL should be included in action result. Got: {action_result_str}"
    )

    # Verify the format shows what happened
    assert "succeeded" in action_result_str
    assert "click" in action_result_str.lower()

    # Create validation message and verify URL context is present
    # Use a mock LLM since we only need to test validation_message() method
    mock_llm = MagicMock()
    validator = CompletionValidator(llm=mock_llm, perception=perception, use_vision=False)

    completion = CompletionAction(success=True, answer="Successfully clicked the Learn more link")

    # Create a minimal observation (simulating we're now on iana.org)
    progress = TrajectoryProgress(current_step=2, max_steps=5)
    mock_obs = Observation.empty()

    validation_msg = validator.validation_message(completion, trajectory, progress, mock_obs)

    # The validation message should contain the URL context
    assert "https://example.com" in validation_msg, (
        f"Validation message should include the URL where the action was executed. Got: {validation_msg}"
    )


def test_validator_accepts_completion_after_page_navigation():
    """
    End-to-end test with real LLM and AgentFallback: Verify that the validator
    correctly accepts a completion after the agent navigated away from the page
    where actions were executed.

    This is the exact scenario that was broken before the fix:
    1. Agent on example.com, user triggers invalid action
    2. AgentFallback kicks in and clicks "Learn more" link (L1)
    3. Page navigates to iana.org
    4. Agent tries to complete: "Successfully clicked the Learn more link"
    5. OLD behavior: Validator rejects because iana.org has no "Learn more" element
    6. NEW behavior: Validator accepts because action history shows the click
       happened on example.com (via URL context)
    """
    with notte.Session(headless=True) as session:
        # Step 1: Navigate to example.com
        session.execute(type="goto", url="https://example.com")
        obs = session.observe()
        assert "example" in obs.metadata.url.lower()

        # Step 2: Use AgentFallback - trigger with invalid action, agent should click the link
        with notte.AgentFallback(
            session,
            task="Click on the 'Learn more' link",
            max_steps=3,
            use_vision=False,
        ) as fallback:
            # Trigger fallback with invalid action
            session.execute(type="click", id="B999999", raise_on_failure=False)

        # Verify we navigated to iana.org (the click worked)
        obs_after = session.observe()
        assert "iana" in obs_after.metadata.url.lower(), (
            f"Expected to navigate to iana.org, but on: {obs_after.metadata.url}"
        )

        # The key assertion: AgentFallback should have succeeded
        # This was the bug - the validator would reject because it saw iana.org elements
        # but the action history said "clicked Learn more" without URL context
        assert fallback.success, (
            "AgentFallback should succeed. Validator should accept completion because "
            "action history now includes URL context showing click was on example.com."
        )
