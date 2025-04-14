import json
from abc import ABC
from typing import Any, Generic, TypeVar

from notte_core.utils.webp_replay import ScreenshotReplay
from pydantic import BaseModel, computed_field

from notte_eval.data.load_data import BenchmarkTask
from notte_eval.evaluators.evaluator import EvaluationResponse

AgentParams = TypeVar("AgentParams")
AgentOut = TypeVar("AgentOut")


class LLMCall(BaseModel):
    class Config:
        frozen: bool = True

    input_tokens: int
    output_tokens: int
    messages_in: list[dict[str, Any]]
    message_out: dict[str, Any]
    pretty_out: str


class Step(BaseModel):
    class Config:
        frozen: bool = True

    url: str
    llm_calls: list[LLMCall]
    duration_in_s: float


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
    def task_id(self) -> int | str:
        return self.task.id

    @computed_field
    def task_website(self) -> str | None:
        return self.task.website_name

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


class AgentBenchmark(ABC, Generic[AgentParams, AgentOut]):
    def __init__(self, params: AgentParams):
        self.params: AgentParams = params

    async def run_agent(self, task: BenchmarkTask) -> AgentOut: ...  # type: ignore[reportUnusedParameter]

    async def process_output(self, task: BenchmarkTask, out: AgentOut) -> TaskResult: ...  # type: ignore[reportUnusedParameter]


class LoggingSink:
    def __init__(self):
        self.messages: list[str] = []

    def write(self, message: str):
        message = message.strip()
        if message:
            self.messages.append(message)
