import asyncio
from typing import Protocol

from notte_core.actions import (
    BaseAction,
    BrowserAction,
    InteractionAction,
)
from notte_core.browser.dom_tree import DomNode, NodeSelectors
from notte_core.browser.snapshot import BrowserSnapshot
from notte_core.common.logging import logger
from notte_core.errors.actions import InvalidActionError
from notte_core.profiling import profiler

from notte_browser.dom.locate import selectors_through_shadow_dom
from notte_browser.errors import FailedNodeResolutionError, NoSnapshotObservedError
from notte_browser.playwright_async_api import ElementHandle


class SelectorGenerator(Protocol):
    """Builds a Playwright selector for an interaction node from its live element handle.

    `selectors` are the node's CSS / XPath selectors (including its parent iframes). Return a selector
    relative to the element's own frame (notte prefixes the parent iframes, unless the selector already
    enters a frame with `internal:control=enter-frame`), or `None` to fall back to the CSS / XPath selectors.
    """

    async def __call__(self, handle: ElementHandle, selectors: NodeSelectors, /) -> str | None: ...


_selector_generator: SelectorGenerator | None = None

# a generator that takes longer than this is abandoned and the CSS / XPath selectors are used
SELECTOR_GENERATOR_TIMEOUT_S: float = 5.0


def set_selector_generator(generator: SelectorGenerator | None) -> None:
    """Install (or remove, with `None`) the selector generator used to resolve interaction nodes.

    By default there is none, and actions use the CSS / XPath selectors computed by the DOM parser.
    With a generator installed, observe also keeps a live element handle per interaction node (in
    `ComputedDomAttributes.handle`), which the generator receives when the node is resolved.
    Install it before observing: snapshots taken earlier have no handles.
    """
    global _selector_generator
    _selector_generator = generator


def get_selector_generator() -> SelectorGenerator | None:
    return _selector_generator


def frame_prefix(selectors: NodeSelectors) -> str:
    """Playwright selector prefix that enters the node's parent iframes, outermost first."""
    return "".join(f"css={path} >> internal:control=enter-frame >> " for path in selectors.iframe_parent_css_selectors)


async def generate_playwright_selector(node: DomNode, selectors: NodeSelectors) -> str | None:
    generator = _selector_generator
    handle = node.computed_attributes.handle
    if generator is None or handle is None:
        return None
    try:
        selector = await asyncio.wait_for(generator(handle, selectors), timeout=SELECTOR_GENERATOR_TIMEOUT_S)
    except Exception as e:
        logger.debug(f"Selector generator failed for node {node.id}, using CSS / XPath selectors: {e}")
        return None
    if not selector:
        return None
    if "internal:control=enter-frame" in selector:
        # the generator already returned a selector rooted at the page
        return selector
    return frame_prefix(selectors) + selector


class NodeResolutionPipe:
    @profiler.profiled(service_name="execution")
    @staticmethod
    async def forward(
        action: BaseAction,
        snapshot: BrowserSnapshot | None,
        verbose: bool = False,
    ) -> InteractionAction | BrowserAction:
        if isinstance(action, BrowserAction):
            # nothing to do here
            return action

        if not isinstance(action, InteractionAction):
            raise InvalidActionError("unknown", f"action is not an interaction action: {action.type}")

        if action.selector is not None:
            return action

        if snapshot is None:
            raise NoSnapshotObservedError()

        # resolve selector
        selector_map: dict[str, DomNode] = {
            inode.id: inode for inode in snapshot.interaction_nodes() if inode.id is not None
        }
        is_id_resolved = action.id in selector_map
        if not is_id_resolved:
            raise InvalidActionError(action_id=action.id, reason=f"action '{action.id}' not found in page context.")
        node = selector_map[action.id]
        action.selector = await NodeResolutionPipe.resolve_selectors(node, verbose)
        action.text_label = node.inner_text()
        return action

    @staticmethod
    async def resolve_selectors(node: DomNode, verbose: bool = False) -> NodeSelectors:
        assert node.id is not None, "Interaction nodes must have an id"
        if node.computed_attributes.selectors is None:
            raise FailedNodeResolutionError(node.id)
        selectors = node.computed_attributes.selectors
        if selectors.in_shadow_root:
            if verbose:
                logger.info(f"🔍 Resolving shadow root selectors for {node.id} ({node.text})")
            selectors = selectors_through_shadow_dom(node)
        if selectors.playwright_selector is None:
            playwright_selector = await generate_playwright_selector(node, selectors)
            if playwright_selector is not None:
                # copy: the snapshot's selectors stay as observed
                selectors = selectors.model_copy(update={"playwright_selector": playwright_selector})
        return selectors
