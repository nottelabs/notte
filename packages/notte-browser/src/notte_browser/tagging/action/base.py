from abc import ABC, abstractmethod
from collections.abc import Sequence

from notte_core.actions.base import BaseAction
from notte_core.actions.space import ActionSpace
from notte_core.browser.snapshot import BrowserSnapshot
from notte_sdk.types import PaginationParams


class BaseActionSpacePipe(ABC):
    @abstractmethod
    def forward(
        self,
        snapshot: BrowserSnapshot,
        previous_action_list: Sequence[BaseAction] | None,
        pagination: PaginationParams,
    ) -> ActionSpace:
        raise NotImplementedError()

    async def forward_async(
        self,
        snapshot: BrowserSnapshot,
        previous_action_list: Sequence[BaseAction] | None,
        pagination: PaginationParams,
    ) -> ActionSpace:
        return self.forward(snapshot, previous_action_list, pagination)
