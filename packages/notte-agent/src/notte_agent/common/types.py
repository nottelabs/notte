import datetime as dt
from typing import Annotated

from litellm import AllMessageValues
from notte_browser.session import SessionTrajectoryStep
from notte_core.agent_types import AgentStepResponse
from notte_core.browser.observation import Screenshot
from notte_core.common.config import ScreenshotType, config
from notte_core.common.tracer import LlmUsageDictTracer
from notte_core.utils.webp_replay import ScreenshotReplay, WebpReplay
from pydantic import BaseModel, Field, computed_field
from typing_extensions import override


class AgentTrajectoryStep(SessionTrajectoryStep):
    agent_response: AgentStepResponse


class AgentResponse(BaseModel):
    success: bool
    answer: str
    trajectory: list[AgentTrajectoryStep]
    # logging information
    created_at: Annotated[dt.datetime, Field(description="The creation time of the agent")]
    closed_at: Annotated[dt.datetime, Field(description="The closed time of the agent")]
    status: str = "closed"
    # only used for debugging purposes
    llm_messages: list[AllMessageValues]
    llm_usage: LlmUsageDictTracer.AggregatedUsage | None

    @computed_field
    @property
    def duration_in_s(self) -> float:
        return (self.closed_at - self.created_at).total_seconds()

    @computed_field
    @property
    def steps(self) -> list[AgentStepResponse]:
        return [step.agent_response for step in self.trajectory]

    @override
    def __str__(self) -> str:
        return (
            f"AgentResponse(success={self.success}, duration_in_s={round(self.duration_in_s, 2)}, answer={self.answer})"
        )

    def screenshots(self) -> list[Screenshot]:
        return [step.obs.screenshot for step in self.trajectory]

    def replay(self, step_texts: bool = True, screenshot_type: ScreenshotType = config.screenshot_type) -> WebpReplay:
        screenshots: list[bytes] = []
        texts: list[str] = []

        for step in self.trajectory:
            screenshots.append(step.obs.screenshot.bytes(screenshot_type))
            texts.append(step.agent_response.state.next_goal)

        if len(screenshots) == 0:
            raise ValueError("No screenshots found in agent trajectory")

        if step_texts:
            return ScreenshotReplay.from_bytes(screenshots).get(step_text=texts)  # pyright: ignore [reportArgumentType]
        else:
            return ScreenshotReplay.from_bytes(screenshots).get()

    @override
    def __repr__(self) -> str:
        return self.__str__()
