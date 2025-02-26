import json
from abc import ABC
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, computed_field

from notte_eval.webvoyager.load_data import WebVoyagerTask
from notte_eval.evaluators.evaluator import EvaluationResponse
from notte_eval.screenshots import Screenshots

AgentParams = TypeVar("AgentParams")
AgentOut = TypeVar("AgentOut")


class LLMCall(BaseModel):
    class Config:
        frozen = True

    input_tokens: int
    output_tokens: int
    messages_in: list[dict[str, Any]]
    message_out: dict[str, Any]


class Step(BaseModel):
    class Config:
        frozen = True

    url: str
    llm_calls: list[LLMCall]
    duration_in_s: float


class TaskResult(BaseModel):
    success: bool
    run_id: int = -1
    eval: EvaluationResponse | None = None
    duration_in_s: float
    agent_answer: str
    task: WebVoyagerTask
    steps: list[Step]
    logs: dict[str, str] = {}
    screenshots: Screenshots

    @computed_field
    def task_description(self) -> str:
        return self.task.question

    @computed_field
    def task_id(self) -> int:
        return self.task.id

    @computed_field
    def task_website(self) -> str:
        return self.task.name

    @computed_field
    def reference_answer(self) -> str:
        return self.task.ref_answers[0].answer

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
        self.params = params

    async def run_agent(self, task: WebVoyagerTask) -> AgentOut: ...

    async def process_output(self, task: WebVoyagerTask, out: AgentOut) -> TaskResult: ...


class LoggingSink:
    def __init__(self):
        self.messages: list[str] = []

    def write(self, message: str):
        message = message.strip()
        if message:
            self.messages.append(message)
