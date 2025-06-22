from notte_core.actions import BaseAction, GotoAction
from notte_core.browser.observation import Observation, TrajectoryProgress
from pydantic import BaseModel, Field

from notte_agent.common.safe_executor import ExecutionStatus
from notte_agent.common.types import AgentStepResponse, AgentTrajectoryStep

ExecutionStepStatus = ExecutionStatus[BaseAction, Observation]


def trim_message(message: str, max_length: int | None = None) -> str:
    if max_length is None or len(message) <= max_length:
        return message
    return f"...{message[-max_length:]}"


class AgentTrajectoryHistory(BaseModel):
    max_steps: int
    steps: list[AgentTrajectoryStep] = Field(default_factory=list)
    max_error_length: int | None = None

    @property
    def progress(self) -> TrajectoryProgress:
        return TrajectoryProgress(
            max_steps=self.max_steps,
            current_step=len(self.steps),
        )

    def reset(self) -> None:
        self.steps = []

    def perceive(self) -> str:
        steps = "\n".join([self.perceive_step(step, step_idx=i) for i, step in enumerate(self.steps)])
        return f"""
[Start of action execution history memory]
{steps or self.start_rules()}
[End of action execution history memory]
    """

    def start_rules(self) -> str:
        return f"""
No action executed so far...
Your first action should always be a `{GotoAction.name()}` action with a url related to the task.
You should reflect what url best fits the task you are trying to solve to start the task, e.g.
- flight search task => https://www.google.com/travel/flights
- go to reddit => https://www.reddit.com
- ...
ONLY if you have ABSOLUTELY no idea what to do, you can use `https://www.google.com` as the default url.
THIS SHOULD BE THE LAST RESORT.
"""

    def perceive_step_result(
        self,
        result: ExecutionStepStatus,
        include_ids: bool = False,
        include_data: bool = False,
    ) -> str:
        return self.perceive_execution_result(
            result, include_ids=include_ids, include_data=include_data, max_error_length=self.max_error_length
        )

    @staticmethod
    def perceive_execution_result(
        result: ExecutionStepStatus,
        include_ids: bool = False,
        include_data: bool = False,
        max_error_length: int | None = None,
    ) -> str:
        action = result.input
        id_str = f" with id={action.id}" if include_ids else ""
        if not result.success:
            err_msg = trim_message(result.message, max_error_length)
            return f"❌ action '{action.name()}'{id_str} failed with error: {err_msg}"
        success_msg = f"✅ action '{action.name()}'{id_str} succeeded: '{action.execution_message()}'"
        data = result.get().data
        if include_data and data is not None and data.structured is not None and data.structured.data is not None:
            return f"{success_msg}\n\nExtracted JSON data:\n{data.structured.data.model_dump_json()}"
        return success_msg

    def perceive_step(
        self,
        step: AgentTrajectoryStep,
        step_idx: int = 0,
        include_ids: bool = False,
        include_data: bool = True,
    ) -> str:
        action_msg = "\n".join(["  - " + result.input.model_dump_agent_json() for result in step.results])
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

    def add_agent_response(self, output: AgentStepResponse) -> None:
        self.steps.append(AgentTrajectoryStep(agent_response=output, results=[]))

    def add_step(self, step: ExecutionStepStatus) -> None:
        if len(self.steps) == 0:
            raise ValueError("Cannot add step to empty trajectory. Use `add_agent_response` first.")
        else:
            if step.output is not None:
                step.output.progress = self.progress
            self.steps[-1].results.append(step)

    def observations(self) -> list[Observation]:
        obs = [obs for step in self.steps for obs in step.observations()]
        for o in obs:
            assert o.progress is not None, "Internal check: progress should be set for all observations"
        return obs

    def last_obs(self) -> Observation | None:
        for step in self.steps[::-1]:
            for step_result in step.results[::-1]:
                if step_result.success and step_result.output is not None:
                    return step_result.output
        return None
