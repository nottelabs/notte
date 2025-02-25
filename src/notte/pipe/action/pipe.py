from collections.abc import Sequence
from enum import StrEnum

from loguru import logger
from pydantic import BaseModel
from typing_extensions import override

from notte.browser.processed_snapshot import ProcessedBrowserSnapshot
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


class MainActionSpaceConfig(BaseModel):
    type: ActionSpaceType = ActionSpaceType.LLM_TAGGING
    llm_tagging: LlmActionSpaceConfig = LlmActionSpaceConfig()
    simple: SimpleActionSpaceConfig = SimpleActionSpaceConfig()
    verbose: bool = False


class MainActionSpacePipe(BaseActionSpacePipe):
    def __init__(self, llmserve: LLMService, config: MainActionSpaceConfig) -> None:
        self.config: MainActionSpaceConfig = config
        self.llmserve: LLMService = llmserve
        self.llm_pipe: LlmActionSpacePipe = LlmActionSpacePipe(llmserve=llmserve, config=self.config.llm_tagging)
        self.simple_pipe: SimpleActionSpacePipe = SimpleActionSpacePipe(config=self.config.simple)

    @override
    def forward(
        self,
        context: ProcessedBrowserSnapshot,
        previous_action_list: Sequence[BaseAction] | None,
        pagination: PaginationParams,
    ) -> BaseActionSpace:
        match self.config.type:
            case ActionSpaceType.LLM_TAGGING:
                if self.config.verbose:
                    logger.info("🏷️ Running LLM tagging action listing")
                return self.llm_pipe.forward(context, previous_action_list, pagination)  # type: ignore
            case ActionSpaceType.SIMPLE:
                if self.config.verbose:
                    logger.info("📋 Running simple action listing")
                return self.simple_pipe.forward(context, previous_action_list, pagination)
