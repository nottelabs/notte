from abc import ABC, abstractmethod
from collections.abc import Sequence

from notte_core.browser.snapshot import BrowserSnapshot
from notte_core.controller.actions import BaseAction
from notte_core.controller.space import BaseActionSpace
from notte_sdk.types import PaginationParams


class BaseActionSpacePipe(ABC):
    @abstractmethod
    def forward(
        self,
        snapshot: BrowserSnapshot,
        previous_action_list: Sequence[BaseAction] | None,
        pagination: PaginationParams,
    ) -> BaseActionSpace:
        raise NotImplementedError()

    async def forward_async(
        self,
        snapshot: BrowserSnapshot,
        previous_action_list: Sequence[BaseAction] | None,
        pagination: PaginationParams,
    ) -> BaseActionSpace:
        return self.forward(snapshot, previous_action_list, pagination)
