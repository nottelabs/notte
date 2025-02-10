from typing import Literal, TypeVar

from loguru import logger
from pydantic import BaseModel, Field, create_model

from notte.common.parser import TaskOutput
from notte.controller.actions import BaseAction, ClickAction, CompletionAction
from notte.controller.space import ActionSpace


class AgentState(BaseModel):
    """Current state of the agent"""

    page_summary: str
    previous_goal_status: Literal["success", "failure", "unknown"]
    previous_goal_eval: str
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
        return action_cls(**self.parameters)


class AgentAction(BaseModel):

    def to_action(self) -> BaseAction:
        field_sets = self.model_fields_set
        if len(field_sets) != 1:
            raise ValueError(f"Multiple actions found in {self.model_dump_json()}")
        action_name = field_sets.pop()
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
    return create_model(AgentAction.__name__, __base__=AgentAction, **fields)


TAgentAction = TypeVar("TAgentAction", bound=AgentAction)

_AgentAction: type[AgentAction] = create_agent_action_model()


class StepAgentOutput(BaseModel):
    state: AgentState
    actions: list[_AgentAction]

    @property
    def output(self) -> TaskOutput | None:
        last_action: CompletionAction | None = getattr(self.actions[-1], CompletionAction.name())
        if last_action is not None:
            return TaskOutput(success=last_action.success, answer=last_action.answer)
        return None

    def get_actions(self, max_actions: int | None = None) -> list[BaseAction]:
        actions: list[BaseAction] = []
        # compute valid list of actions
        for i, _action in enumerate(self.actions):
            is_last = i == len(self.actions) - 1
            actions.append(_action.to_action())
            if not is_last and max_actions is not None and i >= max_actions:
                logger.warning(f"Max actions reached: {max_actions}. Skipping remaining actions.")
                break
            if not is_last and actions[-1].name() == ClickAction.name() and actions[-1].id.startswith("L"):
                logger.warning(f"Removing all actions after link click: {actions[-1].id}")
                # all actions after a link `L` should be removed from the list
                break
        return actions

    def log(self) -> None:
        """Log the agent's output with descriptive emojis for better visualization"""
        # Log previous goal evaluation
        logger.debug(f"🤖 Page summary: {self.state.page_summary}")
        eval_emoji: Literal["👍", "⚠️", "🤔"] = (
            "👍"
            if "Success" in self.state.previous_goal_eval
            else "⚠️" if "Failed" in self.state.previous_goal_eval else "🤔"
        )
        logger.info(f"{eval_emoji} previous goal evaluation: {self.state.previous_goal_eval}")

        # Log memory state
        logger.info(f"💭 Memory: {self.state.memory}")

        # Log next goal
        logger.info(f"🎯 Next Goal: {self.state.next_goal}")

        # Log action (using a gear emoji to represent action execution)
        logger.info(f"🔨  Action: {self.action.model_dump_json(exclude_unset=True)}")

        # Log output if present
        if self.output:
            logger.info(f"📤 Output: {self.output}")
