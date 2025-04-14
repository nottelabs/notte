from collections.abc import Sequence

from loguru import logger
from pydantic import BaseModel, Field
from typing_extensions import override

from notte_core.actions.base import Action, BrowserAction, PossibleAction
from notte_core.controller.actions import AllActionRole, AllActionStatus
from notte_core.controller.space import BaseActionSpace
from notte_core.errors.actions import InvalidActionError
from notte_core.errors.processing import InvalidInternalCheckError


class PossibleActionSpace(BaseModel):
    description: str
    actions: Sequence[PossibleAction]


class ActionSpace(BaseActionSpace):
    raw_actions: Sequence[Action] = Field(description="List of available actions in the current state", exclude=True)

    def __post_init__(self) -> None:
        # filter out special actions
        nb_original_actions = len(self.raw_actions)
        self.raw_actions = [action for action in self.raw_actions if not BrowserAction.is_special(action.id)]
        if len(self.raw_actions) != nb_original_actions:
            logger.warning(
                (
                    "Special actions are not allowed in the action space. "
                    f"Removed {nb_original_actions - len(self.raw_actions)} actions."
                )
            )

        for action in self.raw_actions:
            # check 1: check action id is valid
            if action.role == "other":
                raise InvalidActionError(
                    action.id,
                    f"actions listed in action space should have a valid role (L, B, I), got '{action.id[0]}' .",
                )
            # check 2: actions should have description
            if len(action.description) == 0:
                raise InvalidActionError(action.id, "actions listed in action space should have a description.")

    @override
    def actions(
        self,
        status: AllActionStatus = "valid",
        role: AllActionRole = "all",
        include_browser: bool = False,
    ) -> Sequence[Action]:
        match (status, role):
            case ("all", "all"):
                actions = list(self.raw_actions)
            case ("all", _):
                actions = [action for action in self.raw_actions if action.role == role]
            case (_, "all"):
                actions = [action for action in self.raw_actions if action.status == status]
            case (_, _):
                actions = [action for action in self.raw_actions if action.status == status and action.role == role]

        if include_browser:
            return actions + BrowserAction.list()
        return actions

    @override
    def browser_actions(self) -> Sequence[BrowserAction]:
        return BrowserAction.list()

    @override
    def markdown(self, status: AllActionStatus = "valid", include_browser: bool = True) -> str:
        # Get actions with requested status
        actions_to_format = self.actions(status, include_browser=include_browser)

        # Group actions by category
        grouped_actions: dict[str, list[Action]] = {}
        for action in actions_to_format:
            if len(action.category) == 0:
                # should not happen
                raise InvalidInternalCheckError(
                    check=f"action {action} has no category.",
                    url="unknown url",
                    dev_advice=(
                        "This should technically never happen due to post init checks in `notte.actions.space.py`."
                    ),
                )
            if action.category not in grouped_actions:
                grouped_actions[action.category] = []
            grouped_actions[action.category].append(action)

        # Build markdown output
        output: list[str] = []
        for category, actions in grouped_actions.items():
            if len(output) == 0:
                # no \n at the beginning
                output.append(f"# {category}")
            else:
                output.append(f"\n# {category}")
            # Sort actions by ID lexicographically
            sorted_actions = sorted(actions, key=lambda x: x.id)
            for action in sorted_actions:
                line = f"* {action.id}: {action.description}"
                if len(action.params) > 0:
                    line += f" ({action.params})"
                output.append(line)
        return "\n".join(output)
