from __future__ import annotations

import datetime as dt
from typing import Annotated, Any, Literal

from litellm import AllMessageValues
from notte_browser.session import SessionTrajectoryStep
from notte_core.actions import ActionUnion, BaseAction
from notte_core.common.tracer import LlmUsageDictTracer
from notte_core.utils.webp_replay import ScreenshotReplay, WebpReplay
from notte_sdk.types import render_agent_status
from pydantic import BaseModel, Field, computed_field, field_serializer
from typing_extensions import override


class RelevantInteraction(BaseModel):
    """Interaction ids that can be relevant to the next actions"""

    id: str
    reason: str


class AgentState(BaseModel):
    """Current state of the agent"""

    previous_goal_status: Literal["success", "failure", "unknown"]
    previous_goal_eval: str
    page_summary: str
    relevant_interactions: list[RelevantInteraction]
    memory: str
    next_goal: str


class AgentStepResponse(BaseModel):
    state: AgentState
    action: ActionUnion

    @field_serializer("action")
    def serialize_action(self, action: BaseAction, _info: Any) -> dict[str, Any]:
        # TODO: check if this is correct
        return action.model_dump_agent()

    def log_state(self, colors: bool = True) -> list[tuple[str, dict[str, str]]]:
        action_str = f"   ▶ {self.action.name()} with id {self.action.id}"
        interaction_str = ""
        for interaction in self.state.relevant_interactions:
            interaction_str += f"\n   ▶ {interaction.id}: {interaction.reason}"

        return render_agent_status(
            self.state.previous_goal_status,
            summary=self.state.page_summary,
            goal_eval=self.state.previous_goal_eval,
            memory=self.state.memory,
            next_goal=self.state.next_goal,
            interaction_str=interaction_str,
            action_str=action_str,
            colors=colors,
        )


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

    def screenshots(self) -> list[bytes]:
        return [step.obs.screenshot for step in self.trajectory if step.obs.screenshot is not None]

    def replay(self, step_texts: bool = True) -> WebpReplay:
        screenshots: list[bytes] = []
        texts: list[str] = []

        for step in self.trajectory:
            if step.obs.screenshot is not None:
                screenshots.append(step.obs.screenshot)
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
