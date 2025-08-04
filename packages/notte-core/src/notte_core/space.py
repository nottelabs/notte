import random
import re
from collections.abc import Sequence
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field, computed_field

from notte_core.actions import ActionUnion, BrowserAction, BrowserActionUnion, InteractionAction, InteractionActionUnion
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
    description: Annotated[str, Field(description="Human-readable description of the current web page")]
    interaction_actions: Sequence[InteractionActionUnion] = Field(
        description="List of available interaction actions in the current state"
    )
    category: Annotated[
        SpaceCategory | None,
        Field(description="Category of the action space (e.g., 'homepage', 'search-results', 'item')"),
    ] = None

    @computed_field
    @property
    def actions(self) -> Sequence[ActionUnion]:
        return list(self.interaction_actions) + list(self.browser_actions)

    @computed_field
    @property
    def browser_actions(self) -> list[BrowserActionUnion]:
        return BrowserAction.list()

    def filter(
        self,
        pattern: str | None = None,
        action_ids: list[str] | None = None,
    ) -> "ActionSpace":
        # keep the order of the action_ids
        if action_ids is not None:
            action_dict = {action.id: action for action in self.interaction_actions}
            return ActionSpace(
                description=self.description,
                interaction_actions=[action_dict[action_id] for action_id in action_ids if action_id in action_dict],
            )
        elif pattern is not None:
            return ActionSpace(
                description=self.description,
                interaction_actions=[
                    action
                    for action in self.interaction_actions
                    if re.search(pattern, action.selector.playwright_selector)
                ],
            )
        else:
            return self

    def first(self) -> InteractionAction:
        if len(self.interaction_actions) == 0:
            raise InvalidInternalCheckError(
                check="No interaction actions available",
                url="unknown url",
                dev_advice="This should never happen.",
            )
        return self.interaction_actions[0]

    @staticmethod
    def render_actions(actions: Sequence[ActionUnion]) -> str:
        # Group actions by category
        grouped_actions: dict[str, list[ActionUnion]] = {}
        for action in actions:
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

            def get_sort_key(action: ActionUnion) -> str:
                if isinstance(action, InteractionAction):
                    return action.id
                return action.type

            # Sort actions by ID lexicographically
            sorted_actions = sorted(actions, key=get_sort_key)
            for action in sorted_actions:
                param_str = f"id={action.id}" if isinstance(action, InteractionAction) else ""
                if action.param is not None:
                    if len(param_str) > 0:
                        param_str += ", "
                    param_str += f"{action.param.description()}"
                line = f"* `{action.type}({param_str})`: {action.description}"
                output.append(line)
        return "\n".join(output)

    @computed_field
    @property
    def markdown(self) -> str:
        return ActionSpace.render_actions(self.actions)

    @property
    def interaction_markdown(self) -> str:
        return ActionSpace.render_actions(self.interaction_actions)

    def is_empty(self) -> bool:
        return len(self.interaction_actions) == 0

    def sample(self, type: str | None = None) -> ActionUnion:
        actions = [action for action in self.actions if type is None or action.type == type]
        if len(actions) == 0:
            raise InvalidInternalCheckError(
                check=f"No actions available for sampling. type={type}",
                url="unknown url",
                dev_advice="This should never happen.",
            )
        return random.choice(actions)

    @staticmethod
    def empty(description: str = "No actions available") -> "ActionSpace":
        return ActionSpace(description=description, interaction_actions=[])
