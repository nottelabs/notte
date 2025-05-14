from collections.abc import Sequence
from typing import final

from notte_core.actions.percieved import PerceivedAction
from notte_core.browser.snapshot import BrowserSnapshot


@final
class ActionFilteringPipe:
    @staticmethod
    def forward(
        snapshot: BrowserSnapshot,  # type: ignore[unused-argument]
        actions: Sequence[PerceivedAction],
    ) -> Sequence[PerceivedAction]:
        return actions

    @staticmethod
    def exclude_actions_with_invalid_params(action: PerceivedAction) -> bool:  # type: ignore[unused-argument]
        return False  # TODO.

    @staticmethod
    def exclude_actions_with_invalid_category(action: PerceivedAction) -> bool:  # type: ignore[unused-argument]
        return False  # TODO.

    @staticmethod
    def exclude_actions_with_invalid_description(action: PerceivedAction) -> bool:  # type: ignore[unused-argument]
        return False  # TODO.
