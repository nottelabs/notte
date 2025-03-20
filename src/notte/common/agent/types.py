from __future__ import annotations

from litellm import AllMessageValues
from pydantic import BaseModel
from typing_extensions import override

from notte.common.tools.trajectory_history import TrajectoryStep as AgentTrajectoryStep
from notte.common.tracer import LlmUsageDictTracer
from notte.env import TrajectoryStep
from notte.utils.webp_replay import ScreenshotReplay


class AgentResponse(BaseModel):
    success: bool
    answer: str
    env_trajectory: list[TrajectoryStep]
    agent_trajectory: list[AgentTrajectoryStep[BaseModel]]
    messages: list[AllMessageValues] | None = None
    llm_usage: list[LlmUsageDictTracer.LlmUsage]
    duration_in_s: float = -1

    @override
    def __str__(self) -> str:
        return (
            f"AgentResponse(success={self.success}, duration_in_s={round(self.duration_in_s, 2)}, answer={self.answer})"
        )

    def replay(self) -> bytes:
        screenshots: list[bytes] = [
            obs.screenshot
            for step in self.agent_trajectory
            for obs in step.observations()
            if obs.screenshot is not None
        ]
        if len(screenshots) == 0:
            raise ValueError("No screenshots found in agent trajectory")
        return ScreenshotReplay.from_bytes(screenshots).summary_webp()

    @override
    def __repr__(self) -> str:
        return self.__str__()
