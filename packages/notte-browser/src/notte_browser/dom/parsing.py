import asyncio
import json
from collections.abc import Collection, Iterable
from dataclasses import dataclass
from typing import Any

from notte_core.config import config
from notte_core.dom_tree import DomNode, flush_dom_errors
from notte_core.errors import SnapshotProcessingError
from notte_core.logging import logger
from notte_core.profiling import profiler
from typing_extensions import TypedDict

from notte_browser.dom.builder import RawFrame, RawNode, build_dom_tree
from notte_browser.errors import PlaywrightError
from notte_browser.js import script
from notte_browser.playwright_async_api import ElementHandle, Frame, Page
from notte_browser.resolution import get_selector_generator

DOM_TREE_JS = script("buildDomNode.js")

# each frame's DOM is evaluated up to this many times when the evaluation raises (e.g. mid-navigation)
FRAME_EVALUATION_ATTEMPTS: int = 3
# an iframe whose DOM takes longer than this to evaluate is skipped (the main frame has no limit)
IFRAME_EVALUATION_TIMEOUT_S: float = 10.0


@dataclass
class FrameTree:
    """The DOM payload of one frame, before it is grafted under its iframe element."""

    frame: RawFrame
    # the visible child frames, with the iframe element (in this frame) to graft each one under
    child_frames: list[tuple[Frame, RawNode]]


@profiler.profiled("domforward")
async def parse_dom(page: Page) -> DomNode:
    """Builds the DOM tree of a page, iframes included.

    `buildDomNode.js` builds the payload of one document. It is evaluated in the main frame, then in
    every child frame whose iframe element is visible, and each frame's payload is grafted under its
    iframe element. Evaluating each frame separately (rather than reading `iframe.contentDocument`)
    also covers cross-origin iframes. A child frame that fails to evaluate is skipped. The payloads
    are then turned into `DomNode`s in one pass (see `notte_browser.dom.builder`).
    """
    main = await parse_frames(page)
    dom_tree = build_dom_tree(main, url=page.url)
    if dom_tree is None:
        raise SnapshotProcessingError(page.url, "Failed to parse DOM tree. Dom Tree is empty.")
    flush_dom_errors()
    return dom_tree


@profiler.profiled(service_name="observation")
async def parse_frames(page: Page) -> RawFrame:
    """Evaluates `buildDomNode.js` in every visible frame. Returns the main frame's payload, child frames grafted."""
    js_code = DOM_TREE_JS
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
    main = await evaluate_frame(main_frame, js_code, dom_config, child_frames.get(main_frame, []))

    # graft the frames level by level, evaluating the frames of a level concurrently
    next_highlight_index = max_highlight_index(main.frame.nodes.values()) + 1
    # (frame, its iframe element, the parent frame's offset in the main frame's viewport)
    level = [(frame, iframe, 0.0, 0.0) for frame, iframe in main.child_frames]
    while len(level) > 0:
        frame_trees = await asyncio.gather(
            *(evaluate_iframe(frame, js_code, dom_config, child_frames.get(frame, [])) for frame, *_ in level)
        )
        next_level: list[tuple[Frame, RawNode, float, float]] = []
        for (_, iframe, parent_x, parent_y), frame_tree in zip(level, frame_trees):
            if frame_tree is None:
                continue
            offset = iframe.get("frameOffset") or {"x": 0.0, "y": 0.0}
            x, y = parent_x + offset["x"], parent_y + offset["y"]
            next_highlight_index = shift_frame_nodes(frame_tree.frame.nodes.values(), x, y, next_highlight_index)
            iframe["frame"] = frame_tree.frame
            next_level.extend((child, child_iframe, x, y) for child, child_iframe in frame_tree.child_frames)
        level = next_level
    return main.frame


async def evaluate_iframe(
    frame: Frame, js_code: str, dom_config: dict[str, Any], child_frames: list[Frame]
) -> FrameTree | None:
    """`evaluate_frame` for a child frame: on failure, log and return `None` (the frame is skipped)."""
    try:
        return await asyncio.wait_for(
            evaluate_frame(frame, js_code, dom_config, child_frames), timeout=IFRAME_EVALUATION_TIMEOUT_S
        )
    except PlaywrightError as e:
        logger.warning(f"Skipping iframe {frame.url}: failed to evaluate its DOM: {e}")
    except (SnapshotProcessingError, TimeoutError) as e:
        logger.warning(f"Skipping iframe {frame.url}: could not parse its DOM: {type(e).__name__} {e}")
    return None


@profiler.profiled(service_name="observation")
async def evaluate_frame(
    frame: Frame, js_code: str, dom_config: dict[str, Any], child_frames: list[Frame]
) -> FrameTree:
    """Builds the DOM payload of one frame, and finds the iframe elements of its (visible) child frames."""
    # the iframe element of each child frame, so that the script can mark them in the tree
    handles = await asyncio.gather(*(child.frame_element() for child in child_frames), return_exceptions=True)
    framed = [(child, handle) for child, handle in zip(child_frames, handles) if isinstance(handle, ElementHandle)]
    args = dict(dom_config, frame_elements=[handle for _, handle in framed])
    try:
        result, elements = await _evaluate(frame, js_code, args)
    finally:
        if len(framed) > 0:
            _ = await asyncio.gather(*(handle.dispose() for _, handle in framed), return_exceptions=True)

    if result is None or result["rootId"] is None:
        raise SnapshotProcessingError(frame.url, "Failed to parse HTML to dictionary")
    nodes = result["map"]

    child_frame_nodes: list[tuple[Frame, RawNode]] = []
    for node in nodes.values():
        frame_index = node.get("frameIndex")
        if frame_index is not None:
            child_frame_nodes.append((framed[frame_index][0], node))
        if len(elements) > 0:
            highlight_index = node.get("highlightIndex")
            if highlight_index is not None:
                node["handle"] = elements.get(str(highlight_index))
    return FrameTree(frame=RawFrame(root_id=result["rootId"], nodes=nodes), child_frames=child_frame_nodes)


class _Payload(TypedDict):
    rootId: str | None
    map: dict[str, RawNode]


async def _evaluate(
    frame: Frame, js_code: str, args: dict[str, Any]
) -> tuple[_Payload | None, dict[str, ElementHandle]]:
    """Runs the script in `frame`. Also returns the interaction elements' handles if `collect_elements`."""
    attempt = 1
    while True:
        try:
            if not args["collect_elements"]:
                payload: str | None = await frame.evaluate(js_code, args)
                return _load_payload(payload), {}
            result_handle = await frame.evaluate_handle(js_code, args)
            try:
                payload = await result_handle.evaluate("r => r.payload")
                elements_handle = await result_handle.get_property("elements")
                properties = await elements_handle.get_properties()
                await elements_handle.dispose()
            finally:
                await result_handle.dispose()
            elements = {key: element for key, value in properties.items() if (element := value.as_element())}
            return _load_payload(payload), elements
        except PlaywrightError as e:
            if attempt >= FRAME_EVALUATION_ATTEMPTS:
                raise
            logger.debug(f"DOM evaluation failed in frame {frame.url} (attempt {attempt}), retrying: {e}")
            attempt += 1


def _load_payload(payload: str | None) -> _Payload | None:
    return None if payload is None else json.loads(payload)


def max_highlight_index(nodes: Iterable[RawNode]) -> int:
    return max((index for node in nodes if (index := node.get("highlightIndex")) is not None), default=-1)


def shift_frame_nodes(nodes: Collection[RawNode], x: float, y: float, first_highlight_index: int) -> int:
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
