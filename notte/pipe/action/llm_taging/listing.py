from collections.abc import Sequence

from loguru import logger
from pydantic import BaseModel
from typing_extensions import override

from notte.actions.base import Action, PossibleAction
from notte.actions.space import ActionSpace, PossibleActionSpace
from notte.browser.processed_snapshot import ProcessedBrowserSnapshot
from notte.llms.engine import StructuredContent
from notte.llms.service import LLMService
from notte.pipe.action.llm_taging.base import BaseActionListingPipe, RetryPipeWrapper
from notte.pipe.action.llm_taging.parser import (
    ActionListingParserConfig,
    ActionListingParserPipe,
)
from notte.pipe.rendering.pipe import DomNodeRenderingConfig, DomNodeRenderingPipe


class ActionListingConfig(BaseModel):
    prompt_id: str = "action-listing/optim"
    incremental_prompt_id: str = "action-listing-incr"
    parser: ActionListingParserConfig = ActionListingParserConfig()
    rendering: DomNodeRenderingConfig = DomNodeRenderingConfig()
    max_retries: int | None = 3


class ActionListingPipe(BaseActionListingPipe):

    def __init__(
        self,
        llmserve: LLMService,
        config: ActionListingConfig,
    ) -> None:
        super().__init__(llmserve)
        self.config: ActionListingConfig = config

    def get_prompt_variables(
        self, context: ProcessedBrowserSnapshot, previous_action_list: Sequence[Action] | None
    ) -> dict[str, str]:
        vars = {"document": DomNodeRenderingPipe.forward(context.node, config=self.config.rendering)}
        logger.info(f"🚀 {vars['document']}")
        if previous_action_list is not None:
            vars["previous_action_list"] = ActionSpace(raw_actions=previous_action_list, description="").markdown(
                "all", include_browser=False
            )
        return vars

    def parse_action_listing(self, response: str) -> list[PossibleAction]:
        sc = StructuredContent(
            outer_tag="action-listing",
            inner_tag="markdown",
            fail_if_final_tag=False,
            fail_if_inner_tag=False,
        )
        text = sc.extract(response)  # type: ignore
        try:
            return ActionListingParserPipe.forward(text, self.config.parser)
        except Exception as e:
            logger.error(f"Failed to parse action listing: with content: \n {text}")
            raise e

    def parse_webpage_description(self, response: str) -> str:
        sc = StructuredContent(
            outer_tag="document-summary",
            next_outer_tag="document-analysis",
            fail_if_inner_tag=False,
            fail_if_final_tag=False,
            fail_if_next_outer_tag=False,
        )
        text = sc.extract(response)  # type: ignore
        return text

    @override
    def forward(
        self,
        context: ProcessedBrowserSnapshot,
        previous_action_list: Sequence[Action] | None = None,
    ) -> PossibleActionSpace:
        if previous_action_list is not None and len(previous_action_list) > 0:
            return self.forward_incremental(context, previous_action_list)
        if len(context.interaction_nodes()) == 0:
            logger.error("No interaction nodes found in context. Returning empty action list.")
            return PossibleActionSpace(
                description="Description not available because no interaction actions found",
                actions=[],
            )
        variables = self.get_prompt_variables(context, previous_action_list)
        response = self.llm_completion(self.config.prompt_id, variables)
        return PossibleActionSpace(
            description=self.parse_webpage_description(response),
            actions=self.parse_action_listing(response),
        )

    @override
    def forward_incremental(
        self,
        context: ProcessedBrowserSnapshot,
        previous_action_list: Sequence[Action],
    ) -> PossibleActionSpace:
        incremental_context = context.subgraph_without(previous_action_list)
        if incremental_context is None:
            logger.error(
                "No nodes left in context after filtering of exesting actions "
                f"for url {context.snapshot.metadata.url}. "
                "Returning previous action list..."
            )
            return PossibleActionSpace(
                description="",
                actions=[
                    PossibleAction(
                        id=act.id,
                        description=act.description,
                        category=act.category,
                        params=act.params,
                    )
                    for act in previous_action_list
                ],
            )
        document = DomNodeRenderingPipe.forward(context.node, config=self.config.rendering)
        incr_document = DomNodeRenderingPipe.forward(incremental_context.node, config=self.config.rendering)
        total_length, incremental_length = len(document), len(incr_document)
        reduction_perc = (total_length - incremental_length) / total_length * 100
        logger.info(f"🚀 Forward incremental reduces context length by {reduction_perc:.2f}%")
        variables = self.get_prompt_variables(incremental_context, previous_action_list)
        response = self.llm_completion(self.config.incremental_prompt_id, variables)
        return PossibleActionSpace(
            description=self.parse_webpage_description(response),
            actions=self.parse_action_listing(response),
        )


def MainActionListingPipe(
    llmserve: LLMService,
    config: ActionListingConfig,
) -> BaseActionListingPipe:
    if config.max_retries is not None:
        return RetryPipeWrapper(
            pipe=ActionListingPipe(llmserve=llmserve, config=config),
            max_tries=config.max_retries,
        )
    return ActionListingPipe(llmserve=llmserve, config=config)
