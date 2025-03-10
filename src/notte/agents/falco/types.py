from typing import Any, Literal, TypeVar

from loguru import logger
from pydantic import BaseModel, Field, create_model, field_serializer, field_validator, model_validator

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
    def serialize_actions(self, actions: list[_AgentAction], _info: Any) -> list[dict[str, Any]]:  # type: ignore[reportUnknownParameterType]
        return [action.to_action().dump_dict() for action in actions]  # type: ignore[reportUnknownMemberType]

    @field_validator("actions")
    @classmethod
    def validate_actions(cls, actions: list[_AgentAction]) -> list[_AgentAction]:  # type: ignore[reportUnknownParameterType, reportUnknownVariableType]
        """Validate that the actions list is not empty and contains valid actions."""
        if not actions:
            raise ValueError("Actions list cannot be empty. At least one action must be provided.")
        return actions  # type: ignore[reportUnknownVariableType]

    @model_validator(mode="after")
    def validate_model(self) -> "StepAgentOutput":
        """Validate the entire model to ensure it's in a valid state."""
        # Check if the last action is a CompletionAction when needed
        try:
            # This will raise an IndexError if actions is empty
            if not self.actions:  # type: ignore[reportUnknownMemberType]
                raise IndexError("Actions list is empty")

            # Get the last action
            last_action = self.actions[-1]  # type: ignore[reportUnknownMemberType]

            # Check if we have a valid action
            action_obj = last_action.to_action()  # type: ignore[reportUnknownMemberType]
            _: Any = action_obj  # Use the variable to avoid unused variable warning
        except IndexError:
            # This should be caught by the field_validator, but just in case
            raise ValueError("Actions list cannot be empty. At least one action must be provided.")
        except Exception as e:
            raise ValueError(f"Invalid action in actions list: {e}")

        return self

    def validate_against_observation(self, observation: dict[str, Any]) -> list[str]:
        """
        Validate that all action IDs exist in the observation.

        Args:
            observation: The current observation containing available elements

        Returns:
            List of error messages if any actions reference non-existent elements
        """
        errors: list[str] = []
        available_ids: set[str] = set()

        # Extract available IDs from the observation
        if "elements" in observation:
            for element in observation["elements"]:
                if "id" in element:
                    available_ids.add(str(element["id"]))

        # Check each action's ID against available IDs
        for i, action in enumerate(self.actions):  # type: ignore[reportUnknownMemberType]
            try:
                action_obj = action.to_action()  # type: ignore[reportUnknownMemberType]
                if hasattr(action_obj, "id") and action_obj.id not in available_ids:  # type: ignore[reportUnknownArgumentType, reportUnknownMemberType]
                    errors.append(f"Action {i} references non-existent element ID: {action_obj.id}")  # type: ignore[reportUnknownMemberType]
            except Exception as e:
                errors.append(f"Error validating action {i}: {e}")

        return errors

    @property
    def output(self) -> CompletionAction | None:
        """Get the completion action if the last action is a CompletionAction."""
        if not self.actions:  # type: ignore[reportUnknownMemberType]
            return None

        # Get the CompletionAction name and use it to get the attribute from the last action
        completion_action_name = CompletionAction.name()

        # Get the last action
        last_action = self.actions[-1]  # type: ignore[reportUnknownMemberType]

        # Get the completion action attribute if it exists
        completion_action = getattr(last_action, completion_action_name, None)  # type: ignore[reportUnknownArgumentType]

        if completion_action is not None:
            return CompletionAction(success=completion_action.success, answer=completion_action.answer)
        return None

    def get_actions(self, max_actions: int | None = None) -> list[BaseAction]:
        """Get a list of BaseAction objects from the actions list."""
        if not self.actions:  # type: ignore[reportUnknownMemberType]
            return []

        actions: list[BaseAction] = []
        # compute valid list of actions
        raw_actions = self.actions  # type: ignore[reportUnknownMemberType]

        for i, action in enumerate(raw_actions):  # type: ignore[reportUnknownArgumentType]
            is_last = i == len(raw_actions) - 1  # type: ignore[reportUnknownArgumentType]
            actions.append(action.to_action())  # type: ignore[reportUnknownMemberType]
            if not is_last and max_actions is not None and i >= max_actions:
                logger.warning(f"Max actions reached: {max_actions}. Skipping remaining actions.")
                break
            if not is_last and actions[-1].name() == ClickAction.name() and actions[-1].id.startswith("L"):
                logger.warning(f"Removing all actions after link click: {actions[-1].id}")
                # all actions after a link `L` should be removed from the list
                break
        return actions
