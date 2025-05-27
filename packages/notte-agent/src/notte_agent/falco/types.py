from typing import Any, Literal

from loguru import logger
from notte_core.actions import ActionUnion, BaseAction, ClickAction, CompletionAction
from notte_core.common.config import config
from notte_sdk.types import render_agent_status
from pydantic import BaseModel, Field, field_serializer


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


class StepAgentOutput(BaseModel):
    state: AgentState
    actions: list[ActionUnion] = Field(min_length=1)

    @field_serializer("actions")
    def serialize_actions(self, actions: list[ActionUnion], _info: Any) -> list[dict[str, Any]]:
        return [action.model_dump_agent() for action in actions]

    @property
    def output(self) -> CompletionAction | None:
        if isinstance(self.actions[-1], CompletionAction):
            return self.actions[-1]
        return None

    def get_actions(self) -> list[BaseAction]:
        actions: list[BaseAction] = []
        # compute valid list of actions
        for i, _action in enumerate(self.actions):
            is_last = i == len(self.actions) - 1
            actions.append(_action)
            if not is_last and i >= config.max_actions_per_step:
                logger.warning(f"Max actions reached: {config.max_actions_per_step}. Skipping remaining actions.")
                break
            if not is_last and actions[-1].name() == ClickAction.name() and actions[-1].id.startswith("L"):
                logger.warning(f"Removing all actions after link click: {actions[-1].id}")
                # all actions after a link `L` should be removed from the list
                break
        return actions

    def log_state(self, colors: bool = True) -> list[tuple[str, dict[str, str]]]:
        action_str = ""
        for action in self.actions:
            action_str += f"   ▶ {action.name()} with id {action.id}"

        return render_agent_status(
            self.state.previous_goal_status,
            summary=self.state.page_summary,
            goal_eval=self.state.previous_goal_eval,
            memory=self.state.memory,
            next_goal=self.state.next_goal,
            action_str=action_str,
            colors=colors,
        )
