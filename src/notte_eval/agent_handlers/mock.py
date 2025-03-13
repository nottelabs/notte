from pydantic import BaseModel
from typing_extensions import override

from notte_eval.data.load_data import Task
from notte_eval.screenshots import Screenshots
from notte_eval.task_types import AgentBenchmark, TaskResult


class MockInput(BaseModel):
    a: int
    b: bool


class MockOutput(BaseModel):
    s: str


class MockBench(AgentBenchmark[MockInput, MockOutput]):
    def __init__(self, params: MockInput):
        super().__init__(params)

    @override
    async def run_agent(self, task: Task) -> MockOutput:
        return MockOutput(s=str(self.params.a))

    @override
    async def process_output(self, task: Task, out: MockOutput) -> TaskResult:
        return TaskResult(
            success=False,
            duration_in_s=0,
            agent_answer=out.s,
            task=task,
            steps=[],
            screenshots=Screenshots.from_base64([]),
        )
