from abc import ABC, abstractmethod
from collections.abc import Sequence

from notte_core.actions import InteractionAction
from notte_core.browser.snapshot import BrowserSnapshot
from notte_core.space import ActionSpace
from notte_sdk.types import PaginationParams


class BaseActionSpacePipe(ABC):
    @abstractmethod
    async def forward(
        self,
        snapshot: BrowserSnapshot,
        previous_action_list: Sequence[InteractionAction] | None,
        pagination: PaginationParams,
    ) -> ActionSpace:
        raise NotImplementedError()

    async def forward_async(
        self,
        snapshot: BrowserSnapshot,
        previous_action_list: Sequence[InteractionAction] | None,
        pagination: PaginationParams,
    ) -> ActionSpace:
        return self.forward(snapshot, previous_action_list, pagination)
