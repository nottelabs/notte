from typing import final

from notte.actions.base import Action
from notte.browser.context import Context


@final
class ActionFilteringPipe:

    @staticmethod
    def forward(context: Context, actions: list[Action]) -> list[Action]:
        for action in actions:
            if ActionFilteringPipe.exclude_actions_with_invalid_params(action):
                action.status = "excluded"
            if ActionFilteringPipe.exclude_actions_with_invalid_category(action):
                action.status = "excluded"
            if ActionFilteringPipe.exclude_actions_with_invalid_description(action):
                action.status = "excluded"
        return actions

    @staticmethod
    def exclude_actions_with_invalid_params(action: Action) -> bool:
        return False  # TODO.

    @staticmethod
    def exclude_actions_with_invalid_category(action: Action) -> bool:
        return False  # TODO.

    @staticmethod
    def exclude_actions_with_invalid_description(action: Action) -> bool:
        return False  # TODO.
