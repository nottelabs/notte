import json
from dataclasses import dataclass
from functools import cached_property
from typing import Any

from notte_agent.common.types import AgentResponse
from notte_core.utils.webp_replay import ScreenshotReplay
from notte_eval.evaluators.evaluator import EvaluationResponse
from pydantic import BaseModel, computed_field


@dataclass
class FunctionLog:
    start_time: float
    end_time: float
    input_data: Any
    output_data: Any

    @cached_property
    def duration_in_s(self):
        return self.end_time - self.start_time


class RunOutput(BaseModel):
    logged_data: dict[str, list[FunctionLog]]
    per_step_calls: list[tuple[FunctionLog, dict[str, list[FunctionLog]]]]
    output: AgentResponse


class LLMCall(BaseModel):
    class Config:
        frozen: bool = True

    input_tokens: int
    output_tokens: int
    messages_in: list[dict[str, Any]]
    message_out: dict[str, Any]


class Step(BaseModel):
    class Config:
        frozen: bool = True

    url: str
    llm_calls: list[LLMCall]
    duration_in_s: float


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
    steps: list[Step]
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
    def total_input_tokens(self) -> int:
        return sum(llm_call.input_tokens for step in self.steps for llm_call in step.llm_calls)

    @computed_field
    def total_output_tokens(self) -> int:
        return sum(llm_call.output_tokens for step in self.steps for llm_call in step.llm_calls)

    @computed_field
    def last_message(self) -> str:
        if len(self.steps) == 0:
            return ""

        for step in self.steps[::-1]:
            if len(step.llm_calls) > 0:
                return json.dumps(step.llm_calls[-1].message_out)

        return ""

    @computed_field
    def convert_to_dict(self) -> dict[str, Any]:
        steps_dict_list: list[dict[str, Any]] = [s.model_dump() for s in self.steps]
        return {
            "success": self.success,
            "run_id": self.run_id,
            "duration_in_s": self.duration_in_s,
            "agent_answer": self.agent_answer,
            "steps": steps_dict_list,
            "logs": self.logs,
        }
