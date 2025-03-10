from typing import List
from unittest.mock import MagicMock

import pytest
from pydantic import BaseModel, Field


# Define the models we need for testing
class NudgeHint(BaseModel):
    """A hint or nudge to help the agent get back on track."""

    message: str = Field(..., description="The hint message to provide to the agent")
    reason: str = Field(..., description="The reason why this hint is being provided")
    severity: str = Field(..., description="The severity of the issue (low, medium, high)")


class NudgeAnalysisResult(BaseModel):
    """The result of analyzing the agent's trajectory."""

    needs_nudge: bool = Field(..., description="Whether the agent needs a nudge")
    hints: List[NudgeHint] = Field(default_factory=list, description="List of hints to provide to the agent")

    def get_formatted_hints(self) -> str:
        """Format the hints as a string to be included in the agent's prompt."""
        if not self.needs_nudge or not self.hints:
            return ""

        result = "🚨 **Agent Nudge**:\n\n"
        for hint in self.hints:
            result += f"- {hint.message}\n"
        return result


# Mock classes for testing
class MockAction:
    def __init__(self, name: str, message: str = ""):
        self.action_name = name
        self.action_message = message
        self.id = f"mock-{name}"

    def name(self) -> str:
        return self.action_name

    def execution_message(self) -> str:
        return self.action_message

    def dump_str(self) -> str:
        return f"{self.action_name}({self.action_message})"


class MockAgentState:
    def __init__(self, previous_goal_status="unknown", previous_goal_eval="", page_summary="", next_goal="", memory=""):
        self.previous_goal_status = previous_goal_status
        self.previous_goal_eval = previous_goal_eval
        self.page_summary = page_summary
        self.next_goal = next_goal
        self.memory = memory
        self.relevant_interactions = []


class MockStepAgentOutput:
    def __init__(self, state, actions=None):
        self.state = state
        self.actions = actions or []

    def model_dump_json(self, **kwargs):
        return "{}"


class MockExecutionStatus:
    def __init__(self, input_action, success=True, message=""):
        self.input = input_action
        self.success = success
        self.message = message

    def get(self):
        return None


class MockTrajectoryStep:
    def __init__(self, agent_response, results=None):
        self.agent_response = agent_response
        self.results = results or []


class MockTrajectoryHistory:
    def __init__(self, max_error_length=None):
        self.steps = []
        self.max_error_length = max_error_length

    def reset(self):
        self.steps = []

    def add_output(self, output):
        self.steps.append(MockTrajectoryStep(agent_response=output, results=[]))

    def add_step(self, step):
        if len(self.steps) == 0:
            raise ValueError("Cannot add step to empty trajectory. Use `add_output` first.")
        else:
            self.steps[-1].results.append(step)


# Implementation of NudgePipe for testing
class NudgePipe:
    def __init__(self, llmserve):
        self.llmserve = llmserve

    def forward(self, trajectory, **params):
        # If there are no steps, no nudge is needed
        if not trajectory.steps:
            return NudgeAnalysisResult(needs_nudge=False)

        # Get the last N steps to analyze
        max_steps = params.get("max_steps_to_analyze", 3)
        steps_to_analyze = trajectory.steps[-max_steps:] if len(trajectory.steps) > max_steps else trajectory.steps

        # Check for repeated failures
        failure_threshold = params.get("failure_threshold", 3)
        consecutive_failures = self._count_consecutive_failures(steps_to_analyze)

        # Check for repeated actions
        repeated_actions = self._detect_repeated_actions(steps_to_analyze)

        # If no issues detected, no nudge is needed
        if consecutive_failures < failure_threshold and not repeated_actions:
            return NudgeAnalysisResult(needs_nudge=False)

        # Prepare trajectory summary for LLM analysis
        trajectory_summary = self._prepare_trajectory_summary(steps_to_analyze)

        # Call LLM to analyze the trajectory and generate hints
        try:
            hints = self._generate_hints(trajectory_summary, params.get("max_tokens", 1000))
            return NudgeAnalysisResult(needs_nudge=True, hints=hints)
        except Exception:
            # Fallback to basic hints if LLM fails
            return self._generate_fallback_hints(consecutive_failures, repeated_actions)

    def _count_consecutive_failures(self, steps):
        count = 0
        for step in reversed(steps):
            if any(not result.success for result in step.results):
                count += 1
            else:
                break
        return count

    def _detect_repeated_actions(self, steps):
        if len(steps) < 2:
            return False

        # Check the last 3 actions (if available)
        action_signatures = []
        for step in steps[-3:]:
            for result in step.results:
                action_signatures.append(f"{result.input.name()}:{result.input.execution_message()}")

        # Check if there are duplicates in the action signatures
        return len(action_signatures) != len(set(action_signatures))

    def _prepare_trajectory_summary(self, steps):
        summary = []
        for i, step in enumerate(steps):
            step_summary = f"Step {i + 1}:\n"
            step_summary += f"Goal: {step.agent_response.state.next_goal}\n"

            for j, result in enumerate(step.results):
                action_name = result.input.name()
                action_msg = result.input.execution_message()
                success = "✓" if result.success else "✗"
                error_msg = f" - Error: {result.message}" if not result.success else ""

                step_summary += f"  Action {j + 1}: {action_name} ({action_msg}) {success}{error_msg}\n"

            summary.append(step_summary)

        return "\n".join(summary)

    def _generate_hints(self, trajectory_summary, max_tokens):
        # This would normally call the LLM, but for testing we'll just return what the mock is set to return
        return self.llmserve.structured_completion()

    def _generate_fallback_hints(self, consecutive_failures, repeated_actions):
        hints = []

        if consecutive_failures >= 3:
            hints.append(
                NudgeHint(
                    message="You're encountering repeated failures with your current approach. Try a different strategy or action.",
                    reason="Multiple consecutive action failures detected",
                    severity="high",
                )
            )

        if repeated_actions:
            hints.append(
                NudgeHint(
                    message="You seem to be repeating the same actions. Consider taking a step back and reassessing your approach.",
                    reason="Repeated action pattern detected",
                    severity="medium",
                )
            )

        return NudgeAnalysisResult(needs_nudge=bool(hints), hints=hints)


def create_mock_trajectory(steps_data: List[dict]) -> MockTrajectoryHistory:
    """Create a mock trajectory history with the given steps data."""
    trajectory = MockTrajectoryHistory()

    for step_data in steps_data:
        # Create mock agent response
        agent_response = MockStepAgentOutput(
            state=MockAgentState(
                previous_goal_status=step_data.get("goal_status", "unknown"),
                previous_goal_eval=step_data.get("goal_eval", ""),
                page_summary=step_data.get("page_summary", ""),
                next_goal=step_data.get("next_goal", ""),
            ),
            actions=step_data.get("actions", []),
        )

        # Add output to trajectory
        trajectory.add_output(agent_response)

        # Add results
        for result_data in step_data.get("results", []):
            action = MockAction(
                name=result_data.get("action_name", "unknown"), message=result_data.get("action_message", "")
            )

            result = MockExecutionStatus(
                input_action=action, success=result_data.get("success", True), message=result_data.get("message", "")
            )

            trajectory.add_step(result)

    return trajectory


class TestNudgePipe:
    @pytest.fixture
    def mock_llm_service(self):
        """Create a mock LLM service."""
        mock_service = MagicMock()
        return mock_service

    @pytest.fixture
    def nudge_pipe(self, mock_llm_service):
        """Create a nudge pipe with a mock LLM service."""
        return NudgePipe(mock_llm_service)

    def test_empty_trajectory_no_nudge(self, nudge_pipe):
        """Test that an empty trajectory doesn't need a nudge."""
        trajectory = MockTrajectoryHistory()

        result = nudge_pipe.forward(trajectory, max_steps_to_analyze=3, failure_threshold=3, max_tokens=1000)

        assert result.needs_nudge is False
        assert len(result.hints) == 0

    def test_successful_trajectory_no_nudge(self, nudge_pipe):
        """Test that a successful trajectory doesn't need a nudge."""
        trajectory = create_mock_trajectory(
            [
                {
                    "next_goal": "Go to Google",
                    "results": [{"action_name": "goto", "action_message": "https://google.com", "success": True}],
                },
                {
                    "next_goal": "Search for cats",
                    "results": [{"action_name": "type", "action_message": "cats", "success": True}],
                },
            ]
        )

        result = nudge_pipe.forward(trajectory, max_steps_to_analyze=3, failure_threshold=3, max_tokens=1000)

        assert result.needs_nudge is False
        assert len(result.hints) == 0

    def test_consecutive_failures_needs_nudge(self, nudge_pipe):
        """Test that consecutive failures trigger a nudge."""
        trajectory = create_mock_trajectory(
            [
                {
                    "next_goal": "Go to Google",
                    "results": [{"action_name": "goto", "action_message": "https://google.com", "success": True}],
                },
                {
                    "next_goal": "Click login button",
                    "results": [
                        {
                            "action_name": "click",
                            "action_message": "login",
                            "success": False,
                            "message": "Element not found",
                        }
                    ],
                },
                {
                    "next_goal": "Click login button again",
                    "results": [
                        {
                            "action_name": "click",
                            "action_message": "login",
                            "success": False,
                            "message": "Element not found",
                        }
                    ],
                },
                {
                    "next_goal": "Try another approach",
                    "results": [
                        {
                            "action_name": "click",
                            "action_message": "login",
                            "success": False,
                            "message": "Element not found",
                        }
                    ],
                },
            ]
        )

        # Mock the LLM response
        mock_hints = [
            NudgeHint(
                message="The login button doesn't seem to exist. Try looking for a 'Sign in' button instead.",
                reason="Repeated failures clicking on a non-existent element",
                severity="high",
            )
        ]
        nudge_pipe.llmserve.structured_completion.return_value = mock_hints

        result = nudge_pipe.forward(trajectory, max_steps_to_analyze=3, failure_threshold=3, max_tokens=1000)

        assert result.needs_nudge is True
        assert len(result.hints) == 1
        assert "login button doesn't seem to exist" in result.hints[0].message
        assert result.get_formatted_hints().startswith("🚨 **Agent Nudge**")

    def test_repeated_actions_needs_nudge(self, nudge_pipe):
        """Test that repeated actions trigger a nudge."""
        trajectory = create_mock_trajectory(
            [
                {
                    "next_goal": "Go to Google",
                    "results": [{"action_name": "goto", "action_message": "https://google.com", "success": True}],
                },
                {
                    "next_goal": "Search for cats",
                    "results": [{"action_name": "type", "action_message": "search box", "success": True}],
                },
                {
                    "next_goal": "Search for cats again",
                    "results": [{"action_name": "type", "action_message": "search box", "success": True}],
                },
            ]
        )

        # Mock the LLM response
        mock_hints = [
            NudgeHint(
                message="You're repeating the same typing action. Try pressing Enter or clicking the search button to submit your query.",
                reason="Repeated typing actions without progressing",
                severity="medium",
            )
        ]
        nudge_pipe.llmserve.structured_completion.return_value = mock_hints

        result = nudge_pipe.forward(trajectory, max_steps_to_analyze=3, failure_threshold=3, max_tokens=1000)

        assert result.needs_nudge is True
        assert len(result.hints) == 1
        assert "repeating the same typing action" in result.hints[0].message

    def test_llm_error_fallback_hints(self, nudge_pipe):
        """Test that fallback hints are provided when LLM fails."""
        trajectory = create_mock_trajectory(
            [
                {
                    "next_goal": "Go to Google",
                    "results": [{"action_name": "goto", "action_message": "https://google.com", "success": True}],
                },
                {
                    "next_goal": "Click login button",
                    "results": [
                        {
                            "action_name": "click",
                            "action_message": "login",
                            "success": False,
                            "message": "Element not found",
                        }
                    ],
                },
                {
                    "next_goal": "Click login button again",
                    "results": [
                        {
                            "action_name": "click",
                            "action_message": "login",
                            "success": False,
                            "message": "Element not found",
                        }
                    ],
                },
                {
                    "next_goal": "Try another approach",
                    "results": [
                        {
                            "action_name": "click",
                            "action_message": "login",
                            "success": False,
                            "message": "Element not found",
                        }
                    ],
                },
            ]
        )

        # Make the LLM raise an exception
        nudge_pipe.llmserve.structured_completion.side_effect = Exception("LLM error")

        result = nudge_pipe.forward(trajectory, max_steps_to_analyze=3, failure_threshold=3, max_tokens=1000)

        assert result.needs_nudge is True
        assert len(result.hints) == 2
        assert any("encountering repeated failures" in hint.message for hint in result.hints)
        assert any("high" == hint.severity for hint in result.hints)

    def test_formatting_hints(self):
        """Test that hints are formatted correctly."""
        hints = [
            NudgeHint(message="First hint", reason="First reason", severity="low"),
            NudgeHint(message="Second hint", reason="Second reason", severity="high"),
        ]

        result = NudgeAnalysisResult(needs_nudge=True, hints=hints)
        formatted = result.get_formatted_hints()

        assert "🚨 **Agent Nudge**" in formatted
        assert "- First hint" in formatted
        assert "- Second hint" in formatted

    def test_no_hints_empty_string(self):
        """Test that no hints returns an empty string."""
        result = NudgeAnalysisResult(needs_nudge=False, hints=[])
        assert result.get_formatted_hints() == ""

        result = NudgeAnalysisResult(needs_nudge=True, hints=[])
        assert result.get_formatted_hints() == ""
