from pydantic import BaseModel, Field

from examples.simple.types import StepAgentOutput
from notte.browser.observation import Observation
from notte.common.safe_executor import ExecutionStatus
from notte.controller.actions import BaseAction, GotoAction

ExecutionStepStatus = ExecutionStatus[BaseAction, Observation]


class TrajectoryStep(BaseModel):
    agent_response: StepAgentOutput
    results: list[ExecutionStepStatus]


def trim_message(message: str, max_length: int | None = None) -> str:
    if max_length is None or len(message) <= max_length:
        return message
    return f"...{message[-max_length:]}"


class TrajectoryHistory(BaseModel):
    steps: list[TrajectoryStep] = Field(default_factory=list)
    max_error_length: int | None = None

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
Hint: your first action should always be a `{GotoAction.name()}` action with a url related to the task.
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
    ) -> str:
        action = result.input
        id_str = f" with id={action.id}" if include_ids else ""
        if not result.success:
            err_msg = trim_message(result.message, self.max_error_length)
            return f"[Execution Failure] action '{action.name()}'{id_str} failed with error: {err_msg}"
        return f"[Execution Success] action '{action.name()}'{id_str}: '{action.execution_message()}'"

    def perceive_step(
        self,
        step: TrajectoryStep,
        step_idx: int = 0,
        include_ids: bool = False,
    ) -> str:
        action_msg = "\n".join(["  - " + result.input.dump_str() for result in step.results])
        status_msg = "\n".join(["  - " + self.perceive_step_result(result, include_ids) for result in step.results])
        return f"""
# Execution step {step_idx}
* state: {step.agent_response.state.model_dump_json()}
* selected actions:
{action_msg}
* execution results:
{status_msg}"""

    def add_step(self, output: StepAgentOutput, step: ExecutionStepStatus) -> None:
        if len(self.steps) == 0 or self.steps[-1].agent_response != output:
            self.steps.append(TrajectoryStep(agent_response=output, results=[step]))
        else:
            self.steps[-1].results.append(step)

    def last_obs(self) -> Observation | None:
        for step in self.steps[::-1]:
            for step_result in step.results[::-1]:
                if step_result.success and step_result.output is not None:
                    return step_result.output
        return None
