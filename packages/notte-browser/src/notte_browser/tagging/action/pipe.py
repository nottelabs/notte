from collections.abc import Sequence
from typing import Self

from loguru import logger
from notte_core.actions import InteractionAction
from notte_core.browser.snapshot import BrowserSnapshot
from notte_core.common.config import config
from notte_core.llms.service import LLMService
from notte_core.space import ActionSpace
from notte_sdk.types import PaginationParams
from typing_extensions import override

from notte_browser.tagging.action.base import BaseActionSpacePipe
from notte_browser.tagging.action.llm_taging.pipe import LlmActionSpacePipe
from notte_browser.tagging.action.simple.pipe import SimpleActionSpacePipe


class MainActionSpacePipe(BaseActionSpacePipe):
    def __init__(self, llmserve: LLMService) -> None:
        self.llmserve: LLMService = llmserve
        self.llm_pipe: LlmActionSpacePipe = LlmActionSpacePipe(llmserve=llmserve)
        self.simple_pipe: SimpleActionSpacePipe = SimpleActionSpacePipe()
        self.enable_perception: bool = True

    def with_perception(self, enable_perception: bool) -> Self:
        self.enable_perception = enable_perception
        return self

    @override
    async def forward(
        self,
        snapshot: BrowserSnapshot,
        previous_action_list: Sequence[InteractionAction] | None,
        pagination: PaginationParams,
    ) -> ActionSpace:
        match self.enable_perception:
            case True:
                if config.verbose:
                    logger.trace("🏷️ Running LLM tagging action listing")
                return await self.llm_pipe.forward(snapshot, previous_action_list, pagination)
            case False:
                if config.verbose:
                    logger.trace("📋 Running simple action listing")
                return await self.simple_pipe.forward(snapshot, previous_action_list, pagination)
