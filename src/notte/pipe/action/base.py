from abc import ABC, abstractmethod
from collections.abc import Sequence

from notte.browser.processed_snapshot import ProcessedBrowserSnapshot
from notte.controller.actions import BaseAction
from notte.controller.space import BaseActionSpace
from notte.sdk.types import PaginationParams


class BaseActionSpacePipe(ABC):
    @abstractmethod
    def forward(
        self,
        context: ProcessedBrowserSnapshot,
        previous_action_list: Sequence[BaseAction] | None,
        pagination: PaginationParams,
    ) -> BaseActionSpace:
        raise NotImplementedError()

    async def forward_async(
        self,
        context: ProcessedBrowserSnapshot,
        previous_action_list: Sequence[BaseAction] | None,
        pagination: PaginationParams,
    ) -> BaseActionSpace:
        return self.forward(context, previous_action_list, pagination)
