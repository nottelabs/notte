from pydantic import Field
from typing_extensions import override

from notte.agents.falco.types import StepAgentOutput
from notte.common.tools.trajectory_history import (
    TrajectoryHistory,
    TrajectoryStep,
)


class FalcoTrajectoryHistory(TrajectoryHistory[StepAgentOutput]):
    steps: list[TrajectoryStep[StepAgentOutput]] = Field(default_factory=list)
    max_error_length: int | None = None

    @override
    def perceive_step(
        self,
        step: TrajectoryStep[StepAgentOutput],
        step_idx: int = 0,
        include_ids: bool = False,
        include_data: bool = True,
    ) -> str:
        action_msg = "\n".join(["  - " + result.input.dump_str() for result in step.results])
        status_msg = "\n".join(
            ["  - " + self.perceive_step_result(result, include_ids, include_data) for result in step.results]
        )
        return f"""
# Execution step {step_idx}
* state:
    - page_summary: {step.agent_response.state.page_summary}
    - previous_goal_status: {step.agent_response.state.previous_goal_status}
    - previous_goal_eval: {step.agent_response.state.previous_goal_eval}
    - memory: {step.agent_response.state.memory}
    - next_goal: {step.agent_response.state.next_goal}
* selected actions:
{action_msg}
* execution results:
{status_msg}"""

    @override
    def add_output(self, output: StepAgentOutput) -> None:
        self.steps.append(TrajectoryStep(agent_response=output, results=[]))
