"""
Tests for the Falco agent types.
"""

import pytest
from pydantic import ValidationError

from notte.agents.falco.types import AgentState, RelevantInteraction, StepAgentOutput, _AgentAction
from notte.controller.actions import ClickAction, CompletionAction


def test_step_agent_output_validation():
    """Test that StepAgentOutput validation works correctly."""
    # Create a valid state
    state = AgentState(
        previous_goal_status="success",
        previous_goal_eval="Goal was achieved",
        page_summary="This is a test page",
        relevant_interactions=[RelevantInteraction(id="test_id", reason="test reason")],
        memory="Test memory",
        next_goal="Next goal",
    )

    # Create a valid action
    valid_action = _AgentAction(click=ClickAction(id="test_id"))

    # This should work
    output = StepAgentOutput(state=state, actions=[valid_action])
    assert output is not None
    assert output.state == state
    assert len(output.actions) == 1

    # Test with empty actions list
    with pytest.raises(ValidationError) as excinfo:
        StepAgentOutput(state=state, actions=[])

    # Check that the error message mentions the actions field
    assert "actions" in str(excinfo.value)
    assert "too_short" in str(excinfo.value)


def test_step_agent_output_methods():
    """Test the methods of StepAgentOutput."""
    # Create a valid state
    state = AgentState(
        previous_goal_status="success",
        previous_goal_eval="Goal was achieved",
        page_summary="This is a test page",
        relevant_interactions=[RelevantInteraction(id="test_id", reason="test reason")],
        memory="Test memory",
        next_goal="Next goal",
    )

    # Create a valid action with completion
    completion_action = CompletionAction(success=True, answer="Test answer")
    valid_action = _AgentAction(completion=completion_action)

    # Create a valid output
    output = StepAgentOutput(state=state, actions=[valid_action])

    # Test the output property
    assert output.output is not None
    assert output.output.success is True
    assert output.output.answer == "Test answer"

    # Test the get_actions method
    actions = output.get_actions()
    assert len(actions) == 1

    # Test with empty actions (this shouldn't happen due to validation, but test the method anyway)
    # We need to bypass validation to test this
    output_dict = output.model_dump()
    output_dict["actions"] = []

    # Create a new output with the modified dict, bypassing validation
    output_with_empty_actions = StepAgentOutput.model_construct(**output_dict)

    # Test that get_actions handles empty actions gracefully
    assert len(output_with_empty_actions.get_actions()) == 0
    assert output_with_empty_actions.output is None
