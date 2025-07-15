from typing import Any

from evaluator import EvaluationResponse  # pyright: ignore[reportImplicitRelativeImport]
from notte_agent.common.types import AgentResponse, AgentTrajectoryStep
from notte_core.utils.webp_replay import ScreenshotReplay
from pydantic import BaseModel, computed_field


class RunOutput(BaseModel):
    duration_in_s: float
    output: AgentResponse


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
    logs: dict[str, str] = {}
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
        return {
            "success": self.success,
            "duration_in_s": self.duration_in_s,
            "n_steps": len(self.steps),
            "input_tokens": self.total_input_tokens,
            "output_tokens": self.total_output_tokens,
            "agent_answer": self.agent_answer,
        }
