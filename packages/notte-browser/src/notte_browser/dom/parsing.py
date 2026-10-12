import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from notte_core.browser.dom_tree import DomErrorBuffer
from notte_core.browser.dom_tree import DomNode as NotteDomNode
from notte_core.common.config import config
from notte_core.common.logging import logger
from notte_core.errors.processing import SnapshotProcessingError
from notte_core.profiling import profiler
from typing_extensions import NotRequired, TypedDict

from notte_browser.dom.csspaths import build_csspath
from notte_browser.dom.id_generation import generate_sequential_ids
from notte_browser.dom.types import DOMBaseNode, DOMElementNode, DOMTextNode
from notte_browser.errors import PlaywrightError
from notte_browser.playwright_async_api import ElementHandle, Frame, Page
from notte_browser.resolution import get_selector_generator

DOM_TREE_JS_PATH = Path(__file__).parent / "buildDomNode.js"

# each frame's DOM is evaluated up to this many times when the evaluation raises (e.g. mid-navigation)
FRAME_EVALUATION_ATTEMPTS: int = 3
# an iframe whose DOM takes longer than this to evaluate is skipped (the main frame has no limit)
IFRAME_EVALUATION_TIMEOUT_S: float = 10.0


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
    pointerElement: bool
    disabledReason: str | None
    highlightIndex: int | None
    shadowRoot: bool
    children: list["DomTreeDict"]
    bbox: dict[str, float] | None
    # set on the iframe elements of the frames we graft (see `buildDomNode.js`)
    frameIndex: NotRequired[int]
    frameOffset: NotRequired[dict[str, float]]
    # set by the parser on interaction nodes when a selector generator is installed
    handle: NotRequired[ElementHandle | None]


@dataclass
class FrameTree:
    """The DOM tree of one frame, before it is grafted under its iframe element."""

    root: DomTreeDict
    nodes: list[DomTreeDict]
    # the visible child frames, with the iframe element (in this tree) to graft each one under
    child_frames: list[tuple[Frame, DomTreeDict]]


class ParseDomTreePipe:
    """Builds the DOM tree of a page, iframes included.

    `buildDomNode.js` builds the tree of one document. It is evaluated in the main frame, then in
    every child frame whose iframe element is visible, and each frame's tree is grafted under its
    iframe element. Evaluating each frame separately (rather than reading `iframe.contentDocument`)
    also covers cross-origin iframes. A child frame that fails to evaluate is skipped.
    """

    @profiler.profiled("domforward")
    async def forward(self, page: Page) -> NotteDomNode:
        dom_tree = await self.parse_dom_tree(page)
        dom_tree = generate_sequential_ids(dom_tree)
        notte_dom_tree = dom_tree.to_notte_domnode()
        DomErrorBuffer.flush()
        return notte_dom_tree

    @profiler.profiled(service_name="observation")
    async def parse_dom_tree(self, page: Page) -> DOMBaseNode:
        js_code = DOM_TREE_JS_PATH.read_text()
        dom_config: dict[str, Any] = {
            "highlight_elements": config.highlight_elements,
            "focus_element": config.focus_element,
            "viewport_expansion": config.viewport_expansion,
            "enable_pointer_elements": config.enable_pointer_elements,
            # keep a handle per interaction node only when something will use it
            "collect_elements": get_selector_generator() is not None,
        }
        if config.verbose:
            logger.trace(f"Parsing DOM tree for {page.url} with config: {dom_config}")

        child_frames: dict[Frame, list[Frame]] = {}
        for frame in page.frames:
            if frame.parent_frame is not None and not frame.is_detached():
                child_frames.setdefault(frame.parent_frame, []).append(frame)

        main_frame = page.main_frame
        main = await self.evaluate_frame(main_frame, js_code, dom_config, child_frames.get(main_frame, []))

        # graft the frames level by level, evaluating the frames of a level concurrently
        next_highlight_index = max_highlight_index(main.nodes) + 1
        # (frame, its iframe element, the parent frame's offset in the main frame's viewport)
        level = [(frame, iframe, 0.0, 0.0) for frame, iframe in main.child_frames]
        while len(level) > 0:
            frame_trees = await asyncio.gather(
                *(self.evaluate_iframe(frame, js_code, dom_config, child_frames.get(frame, [])) for frame, *_ in level)
            )
            next_level: list[tuple[Frame, DomTreeDict, float, float]] = []
            for (_, iframe, parent_x, parent_y), frame_tree in zip(level, frame_trees):
                if frame_tree is None:
                    continue
                offset = iframe.get("frameOffset") or {"x": 0.0, "y": 0.0}
                x, y = parent_x + offset["x"], parent_y + offset["y"]
                next_highlight_index = shift_frame_nodes(frame_tree.nodes, x, y, next_highlight_index)
                iframe["children"].append(frame_tree.root)
                next_level.extend((child, child_iframe, x, y) for child, child_iframe in frame_tree.child_frames)
            level = next_level

        parsed = self._parse_node(
            main.root,
            parent=None,
            in_iframe=False,
            in_shadow_root=False,
            iframe_parent_css_paths=[],
            notte_selector=page.url,
        )
        if parsed is None:
            raise SnapshotProcessingError(page.url, f"Failed to parse DOM tree. Dom Tree is empty. {main.root}")
        return parsed

    async def evaluate_iframe(
        self, frame: Frame, js_code: str, dom_config: dict[str, Any], child_frames: list[Frame]
    ) -> FrameTree | None:
        """`evaluate_frame` for a child frame: on failure, log and return `None` (the frame is skipped)."""
        try:
            return await asyncio.wait_for(
                self.evaluate_frame(frame, js_code, dom_config, child_frames), timeout=IFRAME_EVALUATION_TIMEOUT_S
            )
        except PlaywrightError as e:
            logger.warning(f"Skipping iframe {frame.url}: failed to evaluate its DOM: {e}")
        except (SnapshotProcessingError, TimeoutError) as e:
            logger.warning(f"Skipping iframe {frame.url}: could not parse its DOM: {type(e).__name__} {e}")
        return None

    @profiler.profiled(service_name="observation")
    async def evaluate_frame(
        self, frame: Frame, js_code: str, dom_config: dict[str, Any], child_frames: list[Frame]
    ) -> FrameTree:
        """Builds the DOM tree of one frame, and finds the iframe elements of its (visible) child frames."""
        # the iframe element of each child frame, so that the script can mark them in the tree
        handles = await asyncio.gather(*(child.frame_element() for child in child_frames), return_exceptions=True)
        framed = [(child, handle) for child, handle in zip(child_frames, handles) if isinstance(handle, ElementHandle)]
        args = dict(dom_config, frame_elements=[handle for _, handle in framed])
        try:
            result, elements = await self._evaluate(frame, js_code, args)
        finally:
            if len(framed) > 0:
                _ = await asyncio.gather(*(handle.dispose() for _, handle in framed), return_exceptions=True)

        if result is None or result["rootId"] is None:
            raise SnapshotProcessingError(frame.url, "Failed to parse HTML to dictionary")
        root, nodes = self._reconstruct_dom_tree(result)

        child_frame_nodes: list[tuple[Frame, DomTreeDict]] = []
        for node in nodes:
            frame_index = node.get("frameIndex")
            if frame_index is not None:
                child_frame_nodes.append((framed[frame_index][0], node))
            if len(elements) > 0:
                highlight_index = node.get("highlightIndex")
                if highlight_index is not None:
                    node["handle"] = elements.get(str(highlight_index))
        return FrameTree(root=root, nodes=nodes, child_frames=child_frame_nodes)

    async def _evaluate(
        self, frame: Frame, js_code: str, args: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, dict[str, ElementHandle]]:
        """Runs the script in `frame`. Also returns the interaction elements' handles if `collect_elements`."""
        attempt = 1
        while True:
            try:
                if not args["collect_elements"]:
                    result: dict[str, Any] | None = await frame.evaluate(js_code, args)
                    return result, {}
                result_handle = await frame.evaluate_handle(js_code, args)
                try:
                    result = await result_handle.evaluate("r => ({ rootId: r.rootId, map: r.map })")
                    elements_handle = await result_handle.get_property("elements")
                    properties = await elements_handle.get_properties()
                    await elements_handle.dispose()
                finally:
                    await result_handle.dispose()
                elements = {key: element for key, value in properties.items() if (element := value.as_element())}
                return result, elements
            except PlaywrightError as e:
                if attempt >= FRAME_EVALUATION_ATTEMPTS:
                    raise
                logger.debug(f"DOM evaluation failed in frame {frame.url} (attempt {attempt}), retrying: {e}")
                attempt += 1

    def _parse_node(
        self,
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
        notte_selector = ":".join([notte_selector, str(hash(xpath)), str(hash(css_path))])

        if shadow_root:
            in_shadow_root = True

        element_node = DOMElementNode(
            tag_name=tag_name,
            # an iframe element is in an iframe only if its own document is
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
            bbox=node.get("bbox"),
            shadow_root=shadow_root,
            in_shadow_root=in_shadow_root,
            parent=parent,
            playwright_selector=node.get("playwright_selector"),
            python_selector=node.get("python_selector"),
            handle=node.get("handle"),
        )

        if tag_name.lower() == "iframe":
            # the children of an iframe element are the (grafted) frame's document
            in_iframe = True
            in_shadow_root = False
            iframe_parent_css_paths = iframe_parent_css_paths + [css_path]

        children: list[DOMBaseNode] = []
        for child in node.get("children", []):
            if child is not None:
                child_node = self._parse_node(
                    node=child,
                    parent=element_node,
                    in_iframe=in_iframe,
                    iframe_parent_css_paths=iframe_parent_css_paths,
                    notte_selector=notte_selector,
                    in_shadow_root=in_shadow_root,
                )
                if child_node is not None:
                    children.append(child_node)

        element_node.children = children

        return element_node

    def _reconstruct_dom_tree(self, eval_page: dict[str, Any]) -> tuple[DomTreeDict, list[DomTreeDict]]:
        """Nests the script's flat `{id: node}` map. Returns the root and every node of the map."""
        js_node_map: dict[str, Any] = eval_page["map"]
        js_root_id = eval_page["rootId"]

        def rebuild_dom_tree(node_data: dict[str, Any]):
            children_ids = node_data.get("children", [])
            children = [js_node_map[child_id] for child_id in children_ids if child_id in js_node_map]
            node_data["children"] = children

            for child in children:
                _ = rebuild_dom_tree(child)

        root = js_node_map[js_root_id]
        rebuild_dom_tree(root)

        return root, list(js_node_map.values())


def max_highlight_index(nodes: list[DomTreeDict]) -> int:
    return max((index for node in nodes if (index := node.get("highlightIndex")) is not None), default=-1)


def shift_frame_nodes(nodes: list[DomTreeDict], x: float, y: float, first_highlight_index: int) -> int:
    """Moves a child frame's nodes into the main frame's coordinates and highlight indices.

    The script runs in the child frame, so its bounding boxes are relative to the frame's viewport and
    its highlight indices start at 0. `(x, y)` is the frame's position in the main frame's viewport.
    Returns the next free highlight index.
    """
    next_highlight_index = first_highlight_index + max_highlight_index(nodes) + 1
    for node in nodes:
        bbox = node.get("bbox")
        if bbox is not None:
            bbox["x"] += x
            bbox["y"] += y
        highlight_index = node.get("highlightIndex")
        if highlight_index is not None:
            node["highlightIndex"] = highlight_index + first_highlight_index
    return next_highlight_index


dom_tree_parsers = dict(
    default=ParseDomTreePipe(),
)
