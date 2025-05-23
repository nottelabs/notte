from enum import StrEnum
from typing import Self, final

from loguru import logger
from notte_core.browser.allowlist import ActionAllowList
from notte_core.browser.dom_tree import DomNode
from notte_core.common.config import FrozenConfig

from notte_browser.rendering.interaction_only import InteractionOnlyDomNodeRenderingPipe
from notte_browser.rendering.json import JsonDomNodeRenderingPipe
from notte_browser.rendering.markdown import MarkdownDomNodeRenderingPipe
from notte_browser.rendering.pruning import prune_dom_tree


class DomNodeRenderingType(StrEnum):
    INTERACTION_ONLY = "interaction_only"
    JSON = "json"
    MARKDOWN = "markdown"


DEFAULT_INCLUDE_ATTRIBUTES = frozenset(
    [
        "title",
        "type",
        "name",
        "role",
        "tabindex",
        "aria_label",
        "placeholder",
        "value",
        "alt",
        "src",
        "href",
        "aria_expanded",
    ]
)


class DomNodeRenderingConfig(FrozenConfig):
    type: DomNodeRenderingType = DomNodeRenderingType.MARKDOWN
    include_ids: bool = True
    include_attributes: frozenset[str] = DEFAULT_INCLUDE_ATTRIBUTES
    max_len_per_attribute: int | None = 60
    include_text: bool = True
    include_links: bool = True
    prune_dom_tree: bool = True
    allow_list: ActionAllowList | None = None

    def set_allow_list(self: Self, allow_list: ActionAllowList) -> Self:
        return self._copy_and_validate(allow_list=allow_list)

    def set_markdown(self: Self) -> Self:
        return self._copy_and_validate(type=DomNodeRenderingType.MARKDOWN)

    def set_json(self: Self) -> Self:
        return self._copy_and_validate(type=DomNodeRenderingType.JSON)

    def set_interaction_only(self: Self) -> Self:
        return self._copy_and_validate(type=DomNodeRenderingType.INTERACTION_ONLY)


@final
class DomNodeRenderingPipe:
    @staticmethod
    def forward(node: DomNode, config: DomNodeRenderingConfig) -> str:
        if config.prune_dom_tree and config.type != DomNodeRenderingType.INTERACTION_ONLY:
            if config.verbose:
                logger.info("🫧 Pruning DOM tree...")
            node = prune_dom_tree(node)

        # Exclude images if requested
        match config.type:
            case DomNodeRenderingType.INTERACTION_ONLY:
                return InteractionOnlyDomNodeRenderingPipe.forward(
                    node,
                    include_attributes=config.include_attributes,
                    max_len_per_attribute=config.max_len_per_attribute,
                    verbose=config.verbose,
                )
            case DomNodeRenderingType.JSON:
                return JsonDomNodeRenderingPipe.forward(
                    node,
                    include_ids=config.include_ids,
                    include_links=config.include_links,
                    verbose=config.verbose,
                )
            case DomNodeRenderingType.MARKDOWN:
                return MarkdownDomNodeRenderingPipe.forward(
                    node,
                    include_ids=config.include_ids,
                    verbose=config.verbose,
                )
