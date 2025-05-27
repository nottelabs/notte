from enum import StrEnum
from typing import ClassVar, final

from loguru import logger
from notte_core.browser.dom_tree import DomNode
from notte_core.common.config import config

from notte_browser.rendering.interaction_only import InteractionOnlyDomNodeRenderingPipe
from notte_browser.rendering.json import JsonDomNodeRenderingPipe
from notte_browser.rendering.markdown import MarkdownDomNodeRenderingPipe
from notte_browser.rendering.pruning import prune_dom_tree


class DomNodeRenderingType(StrEnum):
    INTERACTION_ONLY = "interaction_only"
    JSON = "json"
    MARKDOWN = "markdown"


@final
class DomNodeRenderingPipe:
    max_len_per_attribute: ClassVar[int | None] = 60
    include_text: ClassVar[bool] = True
    include_links: ClassVar[bool] = True
    prune_dom_tree: ClassVar[bool] = True

    @staticmethod
    def forward(node: DomNode, type: DomNodeRenderingType, include_ids: bool = True) -> str:
        if DomNodeRenderingPipe.prune_dom_tree and type != DomNodeRenderingType.INTERACTION_ONLY:
            if config.verbose:
                logger.info("🫧 Pruning DOM tree...")
            node = prune_dom_tree(node)

        # Exclude images if requested
        match type:
            case DomNodeRenderingType.INTERACTION_ONLY:
                return InteractionOnlyDomNodeRenderingPipe.forward(
                    node,
                    max_len_per_attribute=DomNodeRenderingPipe.max_len_per_attribute,
                    verbose=config.verbose,
                )
            case DomNodeRenderingType.JSON:
                return JsonDomNodeRenderingPipe.forward(
                    node,
                    include_ids=include_ids,
                    include_links=DomNodeRenderingPipe.include_links,
                    verbose=config.verbose,
                )
            case DomNodeRenderingType.MARKDOWN:
                return MarkdownDomNodeRenderingPipe.forward(
                    node,
                    include_ids=include_ids,
                    verbose=config.verbose,
                )
