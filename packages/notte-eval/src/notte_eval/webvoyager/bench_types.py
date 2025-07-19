from typing import Any

from notte_agent.common.types import AgentResponse, AgentTrajectoryStep
from notte_core.agent_types import AgentStepResponse
from notte_core.utils.webp_replay import ScreenshotReplay
from notte_sdk.types import AgentStatusResponse
from pydantic import BaseModel, computed_field

from notte_eval.webvoyager.evaluator import EvaluationResponse


class RunParams(BaseModel):
    use_sdk: bool
    headless: bool
    use_vision: bool
    proxies: bool
    model: str
    user_agent: str | None
    max_steps: int


class RunOutput(BaseModel):
    duration_in_s: float
    output: AgentResponse


class SdkRunOutput(BaseModel):
    duration_in_s: float
    output: AgentStatusResponse
    replay: ScreenshotReplay


class BenchmarkTask(BaseModel):
    question: str
    url: str | None = None
    answer: str | None = None
    id: str | None = None


class TaskResult(BaseModel):
    success: bool
    run_id: int = -1
    eval: EvaluationResponse | None = None
    duration_in_s: float
    agent_answer: str
    task: BenchmarkTask
    total_input_tokens: int
    total_output_tokens: int
    steps: list[AgentTrajectoryStep]
    screenshots: ScreenshotReplay

    @computed_field
    def task_description(self) -> str:
        return self.task.question

    @computed_field
    def task_id(self) -> str | None:
        return self.task.id

    @computed_field
    def reference_answer(self) -> str | None:
        return self.task.answer

    @computed_field
    def convert_to_dict(self) -> dict[str, Any]:
        steps_list: list[dict[str, Any]] = []

        for step in self.steps:
            step_dict = step.model_dump()
            if "obs" in step_dict and "screenshot" in step_dict["obs"]:
                del step_dict["obs"]["screenshot"]
            steps_list.append(step_dict)

        return {
            "success": self.success,
            "duration_in_s": self.duration_in_s,
            "n_steps": len(self.steps),
            "input_tokens": self.total_input_tokens,
            "output_tokens": self.total_output_tokens,
            "agent_answer": self.agent_answer,
            "steps": steps_list,
        }


class SdkTaskResult(BaseModel):
    success: bool
    run_id: int = -1
    eval: EvaluationResponse | None = None
    duration_in_s: float
    agent_answer: str
    task: BenchmarkTask
    total_input_tokens: int
    total_output_tokens: int
    steps: list[AgentStepResponse]
    screenshots: ScreenshotReplay

    @computed_field
    def task_description(self) -> str:
        return self.task.question

    @computed_field
    def task_id(self) -> str | None:
        return self.task.id

    @computed_field
    def reference_answer(self) -> str | None:
        return self.task.answer

    @computed_field
    def convert_to_dict(self) -> dict[str, Any]:
        steps_list = [step.model_dump() for step in self.steps]

        return {
            "success": self.success,
            "duration_in_s": self.duration_in_s,
            "n_steps": len(self.steps),
            "input_tokens": self.total_input_tokens,
            "output_tokens": self.total_output_tokens,
            "agent_answer": self.agent_answer,
            "steps": steps_list,
        }
