from abc import ABC, abstractmethod
from typing import Generic

from notte_core.actions.base import BaseAction, GotoAction
from notte_core.browser.observation import Observation
from notte_core.common.tracer import TStepAgentOutput
from pydantic import BaseModel, Field

from notte_agent.common.safe_executor import ExecutionStatus

ExecutionStepStatus = ExecutionStatus[BaseAction, Observation]


class TrajectoryStep(BaseModel, Generic[TStepAgentOutput]):
    agent_response: TStepAgentOutput
    results: list[ExecutionStepStatus]

    def observations(self) -> list[Observation]:
        return [result.output for result in self.results if result.output is not None]


def trim_message(message: str, max_length: int | None = None) -> str:
    if max_length is None or len(message) <= max_length:
        return message
    return f"...{message[-max_length:]}"


class TrajectoryHistory(BaseModel, ABC, Generic[TStepAgentOutput]):  # type: ignore[reportUnsafeMultipleInheritance]
    steps: list[TrajectoryStep[TStepAgentOutput]] = Field(default_factory=list)
    max_error_length: int | None = None

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
        action = result.input
        id_str = f" with id={action.id}" if include_ids else ""
        if not result.success:
            err_msg = trim_message(result.message, self.max_error_length)
            return f"❌ action '{action.name()}'{id_str} failed with error: {err_msg}"
        success_msg = f"✅ action '{action.name()}'{id_str} succeeded: '{action.execution_message()}'"
        data = result.get().data
        if include_data and data is not None and data.structured is not None and data.structured.data is not None:
            return f"{success_msg}\n\nExtracted JSON data:\n{data.structured.data.model_dump_json()}"
        return success_msg

    @abstractmethod
    def perceive_step(
        self,
        step: TrajectoryStep[TStepAgentOutput],
        step_idx: int = 0,
        include_ids: bool = False,
        include_data: bool = True,
    ) -> str:
        raise NotImplementedError

    @abstractmethod
    def add_output(self, output: TStepAgentOutput) -> None:
        raise NotImplementedError

    def add_step(self, step: ExecutionStepStatus) -> None:
        if len(self.steps) == 0:
            raise ValueError("Cannot add step to empty trajectory. Use `add_output` first.")
        else:
            self.steps[-1].results.append(step)

    def observations(self) -> list[Observation]:
        return [obs for step in self.steps for obs in step.observations()]

    def last_obs(self) -> Observation | None:
        for step in self.steps[::-1]:
            for step_result in step.results[::-1]:
                if step_result.success and step_result.output is not None:
                    return step_result.output
        return None
