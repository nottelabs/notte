from collections.abc import Sequence
from typing import final

from notte.actions.base import Action
from notte.actions.space import ActionSpace
from notte.browser.context import Context


@final
class ActionFilteringPipe:

    @staticmethod
    def forward(context: Context, actions: Sequence[Action]) -> ActionSpace:
        filtered_actions: list[Action] = []
        for action in actions:
            if ActionFilteringPipe.exclude_actions_with_invalid_params(action):
                action.status = "excluded"
            if ActionFilteringPipe.exclude_actions_with_invalid_category(action):
                action.status = "excluded"
            if ActionFilteringPipe.exclude_actions_with_invalid_description(action):
                action.status = "excluded"
            filtered_actions.append(action)
        return ActionSpace(_actions=filtered_actions)

    @staticmethod
    def exclude_actions_with_invalid_params(action: Action) -> bool:
        return False  # TODO.

    @staticmethod
    def exclude_actions_with_invalid_category(action: Action) -> bool:
        return False  # TODO.

    @staticmethod
    def exclude_actions_with_invalid_description(action: Action) -> bool:
        return False  # TODO.
