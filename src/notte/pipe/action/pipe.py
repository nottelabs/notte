from collections.abc import Sequence
from enum import StrEnum
from typing import Self

from loguru import logger
from typing_extensions import override

from notte.browser.snapshot import BrowserSnapshot
from notte.common.config import FrozenConfig
from notte.controller.actions import BaseAction
from notte.controller.space import BaseActionSpace
from notte.llms.service import LLMService
from notte.pipe.action.base import BaseActionSpacePipe
from notte.pipe.action.llm_taging.pipe import LlmActionSpaceConfig, LlmActionSpacePipe
from notte.pipe.action.simple.pipe import SimpleActionSpaceConfig, SimpleActionSpacePipe
from notte.sdk.types import PaginationParams


class ActionSpaceType(StrEnum):
    LLM_TAGGING = "llm_tagging"
    SIMPLE = "simple"


class MainActionSpaceConfig(FrozenConfig):
    type: ActionSpaceType = ActionSpaceType.LLM_TAGGING
    llm_tagging: LlmActionSpaceConfig = LlmActionSpaceConfig()
    simple: SimpleActionSpaceConfig = SimpleActionSpaceConfig()

    def set_llm_tagging(self: Self) -> Self:
        return self._copy_and_validate(type=ActionSpaceType.LLM_TAGGING)

    def set_simple(self: Self) -> Self:
        return self._copy_and_validate(type=ActionSpaceType.SIMPLE)

    def set_type(self: Self, value: ActionSpaceType) -> Self:
        return self._copy_and_validate(type=value)

    def set_llm_tagging_config(self: Self, value: LlmActionSpaceConfig) -> Self:
        return self._copy_and_validate(llm_tagging=value)

    def set_simple_config(self: Self, value: SimpleActionSpaceConfig) -> Self:
        return self._copy_and_validate(simple=value)

    @override
    def set_verbose(self: Self) -> Self:
        return self._copy_and_validate(
            llm_tagging=self.llm_tagging.set_verbose(),
            simple=self.simple.set_verbose(),
            verbose=True,
        )


class MainActionSpacePipe(BaseActionSpacePipe):
    def __init__(self, llmserve: LLMService, config: MainActionSpaceConfig) -> None:
        self.config: MainActionSpaceConfig = config
        self.llmserve: LLMService = llmserve
        self.llm_pipe: LlmActionSpacePipe = LlmActionSpacePipe(llmserve=llmserve, config=self.config.llm_tagging)
        self.simple_pipe: SimpleActionSpacePipe = SimpleActionSpacePipe(config=self.config.simple)

    @override
    def forward(
        self,
        snapshot: BrowserSnapshot,
        previous_action_list: Sequence[BaseAction] | None,
        pagination: PaginationParams,
    ) -> BaseActionSpace:
        match self.config.type:
            case ActionSpaceType.LLM_TAGGING:
                if self.config.verbose:
                    logger.info("🏷️ Running LLM tagging action listing")
                return self.llm_pipe.forward(snapshot, previous_action_list, pagination)
            case ActionSpaceType.SIMPLE:
                if self.config.verbose:
                    logger.info("📋 Running simple action listing")
                return self.simple_pipe.forward(snapshot, previous_action_list, pagination)
