from enum import StrEnum
from typing import final

from pydantic import BaseModel

from notte.browser.dom_tree import DomNode
from notte.browser.node_type import NodeCategory
from notte.pipe.rendering.interaction_only import InteractionOnlyDomNodeRenderingPipe
from notte.pipe.rendering.json import JsonDomNodeRenderingPipe
from notte.pipe.rendering.markdown import MarkdownDomNodeRenderingPipe


class DomNodeRenderingType(StrEnum):
    INTERACTION_ONLY = "interaction_only"
    JSON = "json"
    MARKDOWN = "markdown"


class DomNodeRenderingConfig(BaseModel):
    type: DomNodeRenderingType = DomNodeRenderingType.MARKDOWN
    include_ids: bool = True
    include_images: bool = False
    include_attributes: list[str] | None = None
    include_text: bool = True
    include_links: bool = True


@final
class DomNodeRenderingPipe:

    @staticmethod
    def forward(node: DomNode, config: DomNodeRenderingConfig) -> str:
        # Exclude images if requested
        if not config.include_images:
            node = node.subtree_without(NodeCategory.IMAGE.roles())

        match config.type:
            case DomNodeRenderingType.INTERACTION_ONLY:
                return InteractionOnlyDomNodeRenderingPipe.forward(node)
            case DomNodeRenderingType.JSON:
                return JsonDomNodeRenderingPipe.forward(
                    node,
                    include_ids=config.include_ids,
                    include_links=config.include_links,
                )
            case DomNodeRenderingType.MARKDOWN:
                return MarkdownDomNodeRenderingPipe.forward(
                    node,
                    include_ids=config.include_ids,
                    include_images=config.include_images,
                )
