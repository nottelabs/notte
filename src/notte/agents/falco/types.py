from typing import Any, Literal, TypeVar

from loguru import logger
from pydantic import BaseModel, Field, create_model, field_serializer

from notte.controller.actions import BaseAction, ClickAction, CompletionAction
from notte.controller.space import ActionSpace


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


# TODO: for later when we do a refactoring
class BetterAgentAction(BaseModel):
    """Base class for agent actions with explicit action handling"""

    action_name: str
    parameters: dict[str, str | int | bool | None]

    @classmethod
    def from_action(cls, action: BaseAction) -> "BetterAgentAction":
        return cls(action_name=action.name(), parameters=action.model_dump(exclude={"category", "id"}))

    def to_action(self, space: ActionSpace) -> BaseAction:
        action_cls = space.action_map.get(self.action_name)
        if not action_cls:
            raise ValueError(f"Unknown action type: {self.action_name}")
        return action_cls(**self.parameters)  # type: ignore[arg-type]


class AgentAction(BaseModel):
    def to_action(self) -> BaseAction:
        field_sets = self.model_fields_set
        if len(field_sets) != 1:
            raise ValueError(f"Multiple actions found in {self.model_dump_json()}")
        action_name = list(field_sets)[0]
        return getattr(self, action_name)


def create_agent_action_model() -> type[AgentAction]:
    """Creates a Pydantic model from registered actions"""
    space = ActionSpace(description="does not matter")
    fields = {
        name: (
            ActionModel | None,
            Field(default=None, description=ActionModel.model_json_schema()["properties"]["description"]["default"]),
        )
        for name, ActionModel in space.action_map.items()
    }
    return create_model(AgentAction.__name__, __base__=AgentAction, **fields)  # type: ignore[call-overload]


TAgentAction = TypeVar("TAgentAction", bound=AgentAction)

_AgentAction: type[AgentAction] = create_agent_action_model()


class StepAgentOutput(BaseModel):
    state: AgentState
    actions: list[_AgentAction] = Field(min_length=1)  # type: ignore[type-arg]

    @field_serializer("actions")
    def serialize_actions(self, actions: list[AgentAction], _info: Any) -> list[dict[str, Any]]:
        return [action.to_action().dump_dict() for action in actions]

    @property
    def output(self) -> CompletionAction | None:
        last_action: CompletionAction | None = getattr(self.actions[-1], CompletionAction.name())  # type: ignore[attr-defined]
        if last_action is not None:
            return CompletionAction(success=last_action.success, answer=last_action.answer)
        return None

    def get_actions(self, max_actions: int | None = None) -> list[BaseAction]:
        actions: list[BaseAction] = []
        # compute valid list of actions
        raw_actions: list[AgentAction] = self.actions  # type: ignore[type-assignment]
        for i, _action in enumerate(raw_actions):
            is_last = i == len(raw_actions) - 1
            actions.append(_action.to_action())
            if not is_last and max_actions is not None and i >= max_actions:
                logger.warning(f"Max actions reached: {max_actions}. Skipping remaining actions.")
                break
            if not is_last and actions[-1].name() == ClickAction.name() and actions[-1].id.startswith("L"):
                logger.warning(f"Removing all actions after link click: {actions[-1].id}")
                # all actions after a link `L` should be removed from the list
                break
        return actions

    def pretty_string(self, colors: bool = True) -> str:
        status = self.state.previous_goal_status
        status_emoji: str
        match status:
            case "unknown":
                status_emoji = "❓"
            case "success":
                status_emoji = "✅"
            case "failure":
                status_emoji = "❌"

        def surround_tags(s: str, tags: tuple[str, ...] = ("b", "blue")) -> str:
            if not colors:
                return s

            start = "".join(f"<{tag}>" for tag in tags)
            end = "".join(f"</{tag}>" for tag in reversed(tags))
            return f"{start}{s}{end}"

        action_str = ""
        actions: list[AgentAction] = self.actions  # type: ignore[reportUnkownMemberType]
        for action in actions:
            action_base: BaseAction = action.to_action()
            action_str += f"   ▶ {action_base.name()} with id {action_base.id}"
        return f"""📝 {surround_tags("Current page:")} {self.state.page_summary}
🔬 {surround_tags("Previous goal:")} {status_emoji} {self.state.previous_goal_eval}
🧠 {surround_tags("Memory:")} {self.state.memory}
🎯 {surround_tags("Next goal:")} {self.state.next_goal}
⚡ {surround_tags("Taking action:")}
{action_str}"""
