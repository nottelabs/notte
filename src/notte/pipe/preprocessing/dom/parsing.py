from pathlib import Path

from loguru import logger
from patchright.async_api import Page
from typing_extensions import TypedDict

from notte.browser.dom_tree import DomErrorBuffer
from notte.browser.dom_tree import DomNode as NotteDomNode
from notte.common.config import FrozenConfig
from notte.errors.processing import SnapshotProcessingError
from notte.pipe.preprocessing.a11y.id_generation import simple_generate_sequential_ids
from notte.pipe.preprocessing.dom.csspaths import build_csspath
from notte.pipe.preprocessing.dom.types import DOMBaseNode, DOMElementNode, DOMTextNode

DOM_TREE_JS_PATH = Path(__file__).parent / "buildDomNode.js"


class DomTreeDict(TypedDict):
    type: str
    text: str
    tagName: str | None
    xpath: str | None
    attributes: dict[str, str]
    isVisible: bool
    isInteractive: bool
    isTopElement: bool
    isEditable: bool
    highlightIndex: int | None
    shadowRoot: bool
    children: list["DomTreeDict"]


class DomParsingConfig(FrozenConfig):
    """
    Viewport expansion in pixels.
    This amount will increase the number of elements which are included in the state what the LLM will see.
    - If set to -1, all elements will be included (this leads to high token usage).
    - If set to 0, only the elements which are visible in the viewport will be included.

    """

    highlight_elements: bool = True
    focus_element: int = -1
    viewport_expansion: int = 500  # update from 0


class ParseDomTreePipe:
    @staticmethod
    async def forward(page: Page, config: DomParsingConfig | None = None) -> NotteDomNode:
        config = config or DomParsingConfig()
        dom_tree = await ParseDomTreePipe.parse_dom_tree(page, config)
        dom_tree = simple_generate_sequential_ids(dom_tree)
        notte_dom_tree = dom_tree.to_notte_domnode()
        DomErrorBuffer.flush()
        return notte_dom_tree

    @staticmethod
    async def parse_dom_tree(page: Page, config: DomParsingConfig) -> DOMBaseNode:
        js_code = DOM_TREE_JS_PATH.read_text()
        if config.verbose:
            logger.info(f"Parsing DOM tree for {page.url} with config: {config.model_dump()}")
        node: DomTreeDict | None = await page.evaluate(js_code, config.model_dump())
        if node is None:
            raise SnapshotProcessingError(page.url, "Failed to parse HTML to dictionary")
        parsed = ParseDomTreePipe._parse_node(
            node,
            parent=None,
            in_iframe=False,
            in_shadow_root=False,
            iframe_parent_css_paths=[],
            notte_selector=page.url,
        )
        if parsed is None:
            raise SnapshotProcessingError(page.url, f"Failed to parse DOM tree. Dom Tree is empty. {node}")
        return parsed

    @staticmethod
    def _parse_node(
        node: DomTreeDict,
        parent: "DOMElementNode | None",
        in_iframe: bool,
        in_shadow_root: bool,
        iframe_parent_css_paths: list[str],
        notte_selector: str,
    ) -> DOMBaseNode | None:
        if node.get("type") == "TEXT_NODE":
            text_node = DOMTextNode(
                text=node["text"],
                is_visible=node["isVisible"],
                parent=parent,
            )

            return text_node

        tag_name = node["tagName"]
        attrs = node.get("attributes", {})
        xpath = node["xpath"]

        if tag_name is None:
            if xpath is None and len(attrs) == 0 and len(node.get("children", [])) == 0:
                return None
            raise ValueError(f"Tag name is None for node: {node}")

        highlight_index = node.get("highlightIndex")
        shadow_root = node.get("shadowRoot", False)
        if xpath is None:
            raise ValueError(f"XPath is None for node: {node}")
        css_path = build_csspath(
            tag_name=tag_name,
            xpath=xpath,
            attributes=attrs,
            highlight_index=highlight_index,
        )
        _iframe_parent_css_paths = iframe_parent_css_paths
        notte_selector = ":".join([notte_selector, str(hash(xpath)), str(hash(css_path))])

        if shadow_root:
            in_shadow_root = True

        if tag_name.lower() == "iframe":
            in_iframe = True
            _iframe_parent_css_paths = _iframe_parent_css_paths + [css_path]

        element_node = DOMElementNode(
            tag_name=tag_name,
            in_iframe=in_iframe,
            xpath=xpath,
            css_path=css_path,
            notte_selector=notte_selector,
            iframe_parent_css_selectors=iframe_parent_css_paths,
            attributes=attrs,
            is_visible=node.get("isVisible", False),
            is_interactive=node.get("isInteractive", False),
            is_top_element=node.get("isTopElement", False),
            is_editable=node.get("isEditable", False),
            highlight_index=node.get("highlightIndex"),
            shadow_root=shadow_root,
            in_shadow_root=in_shadow_root,
            parent=parent,
        )

        children: list[DOMBaseNode] = []
        for child in node.get("children", []):
            if child is not None:
                child_node = ParseDomTreePipe._parse_node(
                    node=child,
                    parent=element_node,
                    in_iframe=in_iframe,
                    iframe_parent_css_paths=_iframe_parent_css_paths,
                    notte_selector=notte_selector,
                    in_shadow_root=in_shadow_root,
                )
                if child_node is not None:
                    children.append(child_node)

        element_node.children = children

        return element_node
