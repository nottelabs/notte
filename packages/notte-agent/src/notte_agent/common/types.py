import datetime as dt
from typing import Annotated

from litellm import AllMessageValues
from notte_core.agent_types import AgentCompletion
from notte_core.browser.observation import Screenshot
from notte_core.common.config import ScreenshotType, config
from notte_core.common.tracer import LlmUsageDictTracer
from notte_core.trajectory import Trajectory
from notte_core.utils.webp_replay import ScreenshotReplay, WebpReplay
from pydantic import BaseModel, Field, computed_field
from typing_extensions import override


class AgentResponse(BaseModel):
    class Config:
        arbitrary_types_allowed: bool = True

    success: bool
    answer: str
    trajectory: Trajectory = Field(exclude=True)
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
    def steps(self) -> list[AgentCompletion]:
        return list(self.trajectory.agent_completions())

    @override
    def __str__(self) -> str:
        return (
            f"AgentResponse(success={self.success}, duration_in_s={round(self.duration_in_s, 2)}, answer={self.answer})"
        )

    def screenshots(self) -> list[Screenshot]:
        return [obs.screenshot for obs in self.trajectory.observations()]

    def replay(self, step_texts: bool = True, screenshot_type: ScreenshotType = config.screenshot_type) -> WebpReplay:
        screenshots: list[bytes] = []
        texts: list[str] = []

        for bundle in self.trajectory.step_iterator():
            if bundle.observation is None or bundle.agent_completion is None:
                continue

            screenshots.append(bundle.observation.screenshot.bytes(screenshot_type))
            texts.append(bundle.agent_completion.state.next_goal)

        if len(screenshots) == 0:
            raise ValueError("No screenshots found in agent trajectory")

        if step_texts:
            return ScreenshotReplay.from_bytes(screenshots).get(step_text=texts)  # pyright: ignore [reportArgumentType]
        else:
            return ScreenshotReplay.from_bytes(screenshots).get()

    @override
    def __repr__(self) -> str:
        return self.__str__()
