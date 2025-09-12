import json
from typing import Any, Literal

from loguru import logger
from pydantic import BaseModel, field_serializer, field_validator

from notte_core.actions import ActionUnion, BaseAction, BrowserAction, CompletionAction, GotoAction, InteractionAction


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


def render_agent_status(
    status: str,
    summary: str,
    goal_eval: str,
    memory: str,
    next_goal: str,
    interaction_str: str,
    action_str: str,
    colors: bool = True,
) -> list[tuple[str, dict[str, str]]]:
    status_emoji: str
    match status:
        case "success":
            status_emoji = "✅"
        case "failure":
            status_emoji = "❌"
        case _:
            status_emoji = "❓"

    def surround_tags(s: str, tags: tuple[str, ...] = ("b", "blue")) -> str:
        if not colors:
            return s

        start = "".join(f"<{tag}>" for tag in tags)
        end = "".join(f"</{tag}>" for tag in reversed(tags))
        return f"{start}{s}{end}"

    to_log: list[tuple[str, dict[str, str]]] = [
        (surround_tags("📝 Current page:") + " {page_summary}", dict(page_summary=summary)),
        (
            surround_tags("🔬 Previous goal:") + " {emoji} {eval}",
            dict(emoji=status_emoji, eval=goal_eval),
        ),
        (surround_tags("🧠 Memory:") + " {memory}", dict(memory=memory)),
        (surround_tags("🎯 Next goal:") + " {goal}", dict(goal=next_goal)),
        (surround_tags("🆔 Relevant ids:") + "{interaction_str}", dict(interaction_str=interaction_str)),
        (surround_tags("⚡ Taking action:") + "\n{action_str}", dict(action_str=action_str)),
    ]
    return to_log


class AgentCompletion(BaseModel):
    state: AgentState
    action: ActionUnion

    @field_validator("action", mode="before")
    def validate_action(cls, v: dict[str, Any] | str):
        if isinstance(v, str):
            v = json.loads(v)
        return v

    @field_serializer("action")
    def serialize_action(self, action: BaseAction, _info: Any) -> dict[str, Any]:
        # TODO: check if this is correct
        return action.model_dump_agent()

    @field_serializer("state")
    def serialize_state(self, state: AgentState, _info: Any) -> dict[str, Any]:
        # remove the previous ids as they might have changed
        response = state.model_dump(exclude_none=True)
        if _info.context is not None and _info.context.get("hide_interactions"):
            response["relevant_interactions"] = []
        return response

    def log_state(self, colors: bool = True) -> list[tuple[str, dict[str, str]]]:
        if isinstance(self.action, InteractionAction):
            action_str = f"   ▶ {self.action.name()} with id {self.action.id}"
        elif isinstance(self.action, BrowserAction) and self.action.param is not None:
            param_name = self.action.param.name
            param_value = getattr(self.action, param_name, None)
            action_str = f"   ▶ {self.action.name()} with {param_name}={param_value}"
        else:
            action_str = f"   ▶ {self.action.name()}"

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

    def live_log_state(self, colors: bool = True) -> None:
        for text, data in self.log_state(colors=colors):
            logger.opt(colors=True).info(text, **data)

    def is_completed(self) -> bool:
        return isinstance(self.action, CompletionAction)

    @classmethod
    def initial(cls, url: str):
        return cls(
            state=AgentState(
                previous_goal_status="success",
                previous_goal_eval="Nothing performed yet",
                page_summary="No page summary yet",
                relevant_interactions=[],
                memory="No memory yet",
                next_goal="Start working on the task",
            ),
            action=GotoAction(url=url),
        )
