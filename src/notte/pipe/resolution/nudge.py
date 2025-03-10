from typing import Required, TypedDict, Unpack

from loguru import logger
from pydantic import BaseModel, Field

from notte.common.tools.trajectory_history import TrajectoryHistory, TrajectoryStep
from notte.errors.llm import LLMParsingError
from notte.llms.service import LLMService


class NudgeConfig(TypedDict):
    """Configuration for the nudge pipe."""

    max_steps_to_analyze: Required[int]
    failure_threshold: Required[int]
    max_tokens: Required[int]


class NudgeHint(BaseModel):
    """A hint or nudge to help the agent get back on track."""

    message: str = Field(..., description="The hint message to provide to the agent")
    reason: str = Field(..., description="The reason why this hint is being provided")
    severity: str = Field(..., description="The severity of the issue (low, medium, high)")


class NudgeHints(BaseModel):
    """Container for a list of hints."""

    hints: list[NudgeHint] = Field(default_factory=list, description="List of hints to provide to the agent")


class NudgeAnalysisResult(BaseModel):
    """The result of analyzing the agent's trajectory."""

    needs_nudge: bool = Field(..., description="Whether the agent needs a nudge")
    hints: list[NudgeHint] = Field(default_factory=list, description="List of hints to provide to the agent")

    def get_formatted_hints(self) -> str:
        """Format the hints as a string to be included in the agent's prompt."""
        if not self.needs_nudge or not self.hints:
            return ""

        result = "🚨 **Agent Nudge**:\n\n"
        for hint in self.hints:
            result += f"- {hint.message}\n"
        return result


class NudgePipe:
    """
    A pipe that analyzes the agent's trajectory and provides hints when the agent gets stuck.
    """

    def __init__(self, llmserve: LLMService) -> None:
        self.llmserve: LLMService = llmserve

    def forward(
        self,
        trajectory: TrajectoryHistory,
        **params: Unpack[NudgeConfig],
    ) -> NudgeAnalysisResult:
        """
        Analyze the agent's trajectory and provide hints if needed.

        Args:
            trajectory: The agent's trajectory history
            params: Configuration parameters for the nudge pipe

        Returns:
            NudgeAnalysisResult: The analysis result with hints if needed
        """
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
        except LLMParsingError as e:
            logger.error(f"Failed to generate nudge hints: {e}")
            # Fallback to basic hints if LLM fails
            return self._generate_fallback_hints(consecutive_failures, repeated_actions)

    def _count_consecutive_failures(self, steps: list[TrajectoryStep]) -> int:
        """Count the number of consecutive failures in the recent steps."""
        count = 0
        for step in reversed(steps):
            if any(not result.success for result in step.results):
                count += 1
            else:
                break
        return count

    def _detect_repeated_actions(self, steps: list[TrajectoryStep]) -> bool:
        """Detect if the agent is repeating the same actions."""
        if len(steps) < 2:
            return False

        # Check the last 3 actions (if available)
        action_signatures: list[str] = []
        for step in steps[-3:]:
            for result in step.results:
                action_signatures.append(f"{result.input.name()}:{result.input.execution_message()}")

        # Check if there are duplicates in the action signatures
        action_set = set(action_signatures)
        return len(action_signatures) != len(action_set)

    def _prepare_trajectory_summary(self, steps: list[TrajectoryStep]) -> str:
        """Prepare a summary of the trajectory for LLM analysis."""
        summary: list[str] = []
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

    def _generate_hints(self, trajectory_summary: str, max_tokens: int) -> list[NudgeHint]:
        """Generate hints using the LLM based on the trajectory summary."""
        variables = {
            "trajectory_summary": trajectory_summary,
            # We're using max_tokens in the variables to avoid the unused parameter warning
            "max_tokens": max_tokens,
        }

        response = self.llmserve.structured_completion(
            prompt_id="agent/nudge", response_format=NudgeHints, variables=variables
        )

        return response.hints

    def _generate_fallback_hints(self, consecutive_failures: int, repeated_actions: bool) -> NudgeAnalysisResult:
        """Generate fallback hints if LLM analysis fails."""
        hints: list[NudgeHint] = []

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
