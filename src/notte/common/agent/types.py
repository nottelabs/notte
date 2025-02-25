from typing_extensions import override
from litellm import AllMessageValues
from pydantic import BaseModel

from notte.common.tools.trajectory_history import TrajectoryStep as AgentTrajectoryStep
from notte.common.tracer import LlmUsageDictTracer
from notte.env import TrajectoryStep


class AgentRequest(BaseModel):
    task: str
    url: str | None = None


class AgentResponse(BaseModel):
    answer: str
    success: bool
    env_trajectory: list[TrajectoryStep]
    agent_trajectory: list[AgentTrajectoryStep]
    messages: list[AllMessageValues] | None = None
    llm_usage: list[LlmUsageDictTracer.LlmUsage]
    duration_in_s: float = -1

    @override
    def __str__(self) -> str:
        return (
            f"AgentResponse(success={self.success}, duration_in_s={round(self.duration_in_s, 2)}, answer={self.answer})"
        )

    @override
    def __repr__(self) -> str:
        return self.__str__()
