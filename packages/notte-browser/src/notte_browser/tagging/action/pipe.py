from collections.abc import Sequence

from notte_core.actions import InteractionAction
from notte_core.browser.snapshot import BrowserSnapshot
from notte_core.common.config import config
from notte_core.common.logging import logger
from notte_core.space import ActionSpace
from notte_sdk.types import PaginationParams
from typing_extensions import override

from notte_browser.tagging.action.base import BaseActionSpacePipe
from notte_browser.tagging.action.simple.pipe import SimpleActionSpacePipe


class MainActionSpacePipe(BaseActionSpacePipe):
    """Lists the interaction actions available on a page from its DOM, without any LLM call."""

    def __init__(self) -> None:
        self.simple_pipe: SimpleActionSpacePipe = SimpleActionSpacePipe()

    @override
    async def forward(
        self,
        snapshot: BrowserSnapshot,
        previous_action_list: Sequence[InteractionAction] | None,
        pagination: PaginationParams,
    ) -> ActionSpace:
        if config.verbose:
            logger.trace("📋 Running simple action listing")
        return await self.simple_pipe.forward(snapshot, previous_action_list, pagination)
