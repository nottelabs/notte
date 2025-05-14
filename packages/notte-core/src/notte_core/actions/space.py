import random
from collections.abc import Sequence
from enum import StrEnum
from typing import Annotated

from loguru import logger
from pydantic import BaseModel, Field, computed_field

from notte_core.actions.base import (
    ActionRole,
    BaseAction,
    BrowserAction,
    InteractionAction,
    ToolAction,
)
from notte_core.actions.percieved import PerceivedAction
from notte_core.errors.actions import InvalidActionError
from notte_core.errors.processing import InvalidInternalCheckError


class SpaceCategory(StrEnum):
    HOMEPAGE = "homepage"
    SEARCH_RESULTS = "search-results"
    DATA_FEED = "data-feed"
    ITEM = "item"
    AUTH = "auth"
    FORM = "form"
    MANAGE_COOKIES = "manage-cookies"
    OVERLAY = "overlay"
    PAYMENT = "payment"
    CAPTCHA = "captcha"
    OTHER = "other"

    def is_data(self) -> bool:
        return self.value in [
            SpaceCategory.DATA_FEED.value,
            SpaceCategory.SEARCH_RESULTS.value,
            SpaceCategory.ITEM.value,
        ]


class ActionSpace(BaseModel):
    interaction_actions: Sequence[PerceivedAction] = Field(
        description="All interaction actions available in the current web page (i.e click, fill, check, etc.)"
    )
    description: Annotated[str, Field(description="Human-readable description of the current web page")]
    category: Annotated[
        SpaceCategory | None,
        Field(description="Category of the action space (e.g., 'homepage', 'search-results', 'item)"),
    ] = None

    @computed_field
    @property
    def browser_actions(self) -> Sequence[ToolAction]:
        """
        All browser actions available in the current web page (i.e go back, go forward, refresh, etc.)
        """
        return BrowserAction.tools()

    @computed_field
    @property
    def actions(self) -> Sequence[BaseAction]:
        """
        All actions available in the current web page
        """
        return list(self.check_interaction_actions()) + list(self.browser_actions)

    @computed_field
    @property
    def markdown(self) -> str:
        """
        Markdown description of all actions available in the current web page
        """
        return self.render(include_browser=True)

    def check_interaction_actions(self) -> Sequence[InteractionAction]:
        checked_actions = [action for action in self.interaction_actions if action.role != "special"]
        if len(checked_actions) != len(self.interaction_actions):
            logger.warning(
                (
                    "Special actions are not allowed in the action space. "
                    f"Removed {len(self.interaction_actions) - len(checked_actions)} actions."
                )
            )

        for action in checked_actions:
            # check 1: check action id is valid
            if action.role == "other":
                raise InvalidActionError(
                    action.id,
                    f"actions listed in action space should have a valid role (L, B, I), got '{action.id[0]}' .",
                )
            # check 2: actions should have description
            if len(action.description) == 0:
                raise InvalidActionError(action.id, "actions listed in action space should have a description.")
        return checked_actions

    def filter(self, role: ActionRole | None = None) -> Sequence[BaseAction]:
        match role:
            case None:
                return self.actions
            case role:
                return [action for action in self.actions if action.role == role]

    def render(self, include_browser: bool = True) -> str:
        # Get actions with requested status
        actions_to_format = self.interaction_actions if not include_browser else self.actions
        if len(actions_to_format) == 0:
            return "No actions available"

        # Group actions by category
        grouped_actions: dict[str, list[BaseAction]] = {}
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
                action_params = getattr(action, "params", [])
                if len(action_params) > 0:
                    line += f" ({action_params})"
                output.append(line)
        return "\n".join(output)

    def sample(self, role: ActionRole | None = None) -> BaseAction:
        return random.choice(self.filter(role))
