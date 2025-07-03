import datetime as dt
import json
from typing import Annotated, Any, Literal

from litellm import AllMessageValues
from loguru import logger
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
    llm_usage: list[LlmUsageDictTracer.LlmUsage]

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

    def save_trajectory(
        self, file_path: str, id_type: Literal["selector", "id"] = "selector", only_success: bool = True
    ) -> None:
        if not file_path.endswith(".json"):
            raise ValueError("File path must end with .json")
        actions: list[dict[str, Any]] = []
        for step in self.trajectory:
            if only_success and not step.result.success:
                continue
            exclude_fields = step.action.non_agent_fields()
            if id_type == "selector":
                exclude_fields.add("id")
                exclude_fields.remove("selector")
                exclude_fields.remove("option_selector")
            exclude_fields.remove("text_label")
            if "value" in exclude_fields:
                exclude_fields.remove("value")
            logger.info(f"Excluding fields: {exclude_fields}")
            actions.append(step.action.model_dump(exclude=exclude_fields, exclude_none=True))
            # actions.append(result.action)
        with open(file_path, "w") as f:
            json.dump(dict(actions=actions), f, indent=4)

    @override
    def __repr__(self) -> str:
        return self.__str__()
