from collections.abc import Sequence
from typing import ClassVar

from loguru import logger
from notte_core.actions.base import Action, PossibleAction
from notte_core.actions.space import ActionSpace, PossibleActionSpace
from notte_core.browser.snapshot import BrowserSnapshot
from notte_core.common.config import config
from notte_core.llms.engine import StructuredContent
from notte_core.llms.service import LLMService
from typing_extensions import override

from notte_browser.rendering.pipe import DomNodeRenderingPipe, DomNodeRenderingType
from notte_browser.tagging.action.llm_taging.base import BaseActionListingPipe, RetryPipeWrapper
from notte_browser.tagging.action.llm_taging.parser import ActionListingParserPipe


class ActionListingPipe(BaseActionListingPipe):
    prompt_id: ClassVar[str] = "action-listing/optim"
    incremental_prompt_id: ClassVar[str] = "action-listing-incr"
    max_retries: ClassVar[int | None] = 3
    rendering_type: ClassVar[DomNodeRenderingType] = DomNodeRenderingType.MARKDOWN

    def __init__(
        self,
        llmserve: LLMService,
    ) -> None:
        super().__init__(llmserve)

    def get_prompt_variables(
        self, snapshot: BrowserSnapshot, previous_action_list: Sequence[Action] | None
    ) -> dict[str, str]:
        vars = {"document": DomNodeRenderingPipe.forward(snapshot.dom_node, type=self.rendering_type)}
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
        text = sc.extract(response)
        try:
            return ActionListingParserPipe.forward(text)
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
        text = sc.extract(response)
        return text

    @override
    def forward(
        self,
        snapshot: BrowserSnapshot,
        previous_action_list: Sequence[Action] | None = None,
    ) -> PossibleActionSpace:
        if previous_action_list is not None and len(previous_action_list) > 0:
            return self.forward_incremental(snapshot, previous_action_list)
        if len(snapshot.interaction_nodes()) == 0:
            if config.verbose:
                logger.error("No interaction nodes found in context. Returning empty action list.")
            return PossibleActionSpace(
                description="Description not available because no interaction actions found",
                actions=[],
            )
        variables = self.get_prompt_variables(snapshot, previous_action_list)
        response = self.llm_completion(self.prompt_id, variables)
        return PossibleActionSpace(
            description=self.parse_webpage_description(response),
            actions=self.parse_action_listing(response),
        )

    @override
    def forward_incremental(
        self,
        snapshot: BrowserSnapshot,
        previous_action_list: Sequence[Action],
    ) -> PossibleActionSpace:
        incremental_snapshot = snapshot.subgraph_without(previous_action_list)
        if incremental_snapshot is None:
            if config.verbose:
                logger.error(
                    (
                        "No nodes left in context after filtering of exesting actions "
                        f"for url {snapshot.metadata.url}. "
                        "Returning previous action list..."
                    )
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
        document = DomNodeRenderingPipe.forward(snapshot.dom_node, type=self.rendering_type)
        incr_document = DomNodeRenderingPipe.forward(incremental_snapshot.dom_node, type=self.rendering_type)
        total_length, incremental_length = len(document), len(incr_document)
        reduction_perc = (total_length - incremental_length) / total_length * 100
        if config.verbose:
            logger.info(f"🚀 Forward incremental reduces context length by {reduction_perc:.2f}%")
        variables = self.get_prompt_variables(incremental_snapshot, previous_action_list)
        response = self.llm_completion(self.incremental_prompt_id, variables)
        return PossibleActionSpace(
            description=self.parse_webpage_description(response),
            actions=self.parse_action_listing(response),
        )


def MainActionListingPipe(
    llmserve: LLMService,
) -> BaseActionListingPipe:
    if ActionListingPipe.max_retries is not None:
        return RetryPipeWrapper(
            pipe=ActionListingPipe(llmserve=llmserve),
            max_tries=ActionListingPipe.max_retries,
            verbose=config.verbose,
        )
    return ActionListingPipe(llmserve=llmserve)
