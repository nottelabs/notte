from litellm import AllMessageValues
from pydantic import BaseModel

from notte.common.tools.trajectory_history import TrajectoryStep as AgentTrajectoryStep
from notte.common.tracer import LlmUsageDictTracer
from notte.env import TrajectoryStep


class AgentOutput(BaseModel):
    answer: str
    success: bool
    env_trajectory: list[TrajectoryStep]
    agent_trajectory: list[AgentTrajectoryStep]
    messages: list[AllMessageValues] | None = None
    llm_usage: list[LlmUsageDictTracer.LlmUsage]
    duration_in_s: float = -1
