from loguru import logger
from notte_core.browser.dom_tree import DomNode, NodeSelectors
from notte_core.common.config import config

from notte_browser.errors import InvalidLocatorRuntimeError, PlaywrightTimeoutError
from notte_browser.playwright_async_api import FrameLocator, Locator, Page


async def locale_element_in_iframes(page: Page, selectors: NodeSelectors) -> FrameLocator | Page:
    if not selectors.in_iframe:
        raise ValueError("Node is not in an iframe")

    iframes_css_paths = selectors.iframe_parent_css_selectors
    if len(iframes_css_paths) == 0:
        raise ValueError("Node is not in an iframe")

    current_frame: FrameLocator | Page = page
    for css_path in iframes_css_paths:
        current_frame = current_frame.frame_locator(css_path)

    return current_frame


async def locate_element(page: Page, selectors: NodeSelectors) -> Locator:
    frame: Page | FrameLocator = page

    if selectors.in_iframe:
        frame = await locale_element_in_iframes(page, selectors)
    # regular case, locate element + scroll into view if needed
    if selectors.playwright_selector is not None:
        # for playwright we wait for the element to be visible
        locator = frame.locator(selectors.playwright_selector)
        if selectors.playwright_selector == "html":
            return locator
        try:
            _ = await locator.wait_for(state="visible", timeout=config.timeout_action_ms * 2)
        except PlaywrightTimeoutError:
            raise InvalidLocatorRuntimeError("Element is not visible", selector=selectors.playwright_selector)

    for selector in selectors.selectors():
        locator = frame.locator(selector)
        count = await locator.count()
        if count > 1:
            logger.debug(f"Found {count} elements for '{selector}'. Check out the dom tree for more details.")
        elif count == 1:
            return locator
    raise InvalidLocatorRuntimeError("count=0 for selector", selector=selectors.selectors()[0])


def selectors_through_shadow_dom(node: DomNode) -> NodeSelectors:
    root_selectors = node.computed_attributes.selectors
    if root_selectors is None:
        raise ValueError(f"Node id={node.id} has no selectors")
    xpaths = [f"xpath={root_selectors.xpath_selector}"]
    while node.parent is not None:
        selectors = node.computed_attributes.selectors
        if selectors is None:
            raise ValueError("Is this a valid dom tree?")
        elif node.computed_attributes.shadow_root:
            if len(selectors.xpath_selector) == 0:
                if node.attributes is None:
                    raise ValueError(f"Node id={node.id} has no attributes")
                logger.debug(
                    (
                        f"Unexpected case during shadow root xpath resolution for node '{node.id}'. "
                        f"Empty xpath. Using tag_name = {node.attributes.tag_name} instead."
                    )
                )
                xpaths.append(node.attributes.tag_name)
            else:
                # xpaths of children also contain xpaths part of parent that we need to remove for shadow root handling
                xpaths[-1] = xpaths[-1].replace(selectors.xpath_selector, "")
                if node.parent.parent is None:
                    xpaths.append(selectors.xpath_selector)
                else:
                    xpaths.append(f"xpath={selectors.xpath_selector}")
        node = node.parent

    shadow_locator = " >> ".join(xpaths[::-1])
    # shadow_locator_css = " >> css=".join(css[::-1])
    return NodeSelectors(
        # override xpath and css selectors to include the shadow dom
        xpath_selector=shadow_locator,
        css_selector=root_selectors.css_selector,
        # keep the rest of the selectors
        in_iframe=root_selectors.in_iframe,
        iframe_parent_css_selectors=root_selectors.iframe_parent_css_selectors,
        notte_selector=root_selectors.notte_selector,
        playwright_selector=root_selectors.playwright_selector,
        in_shadow_root=root_selectors.in_shadow_root,
        python_selector=root_selectors.python_selector,
    )


def locate_file_upload_element(node: DomNode) -> DomNode | None:
    def is_file_input(node: DomNode) -> bool:
        attr = node.attributes
        if attr is None:
            return False
        return attr.tag_name == "input" and attr.type == "file"

    def find_element_by_id(node: DomNode, element_id: str) -> DomNode | None:
        if node.attributes is not None and node.attributes.id_name == element_id:
            return node
        for child in node.children:
            result = find_element_by_id(child, element_id)
            if result:
                return result
        return None

    def get_root(node: DomNode) -> DomNode:
        root = node
        while root.parent:
            root = root.parent
        return root

    # Recursively search for file input in node and its children
    def find_file_input_recursive(node: DomNode, max_depth: int = 3, current_depth: int = 0) -> DomNode | None:
        if current_depth > max_depth:
            return None

        # Check current element
        if is_file_input(node):
            return node

        # Recursively check children
        if node.children and current_depth < max_depth:
            for child in node.children:
                result = find_file_input_recursive(child, max_depth, current_depth + 1)
                if result:
                    return result
        return None

    # Check if current element is a file input
    if is_file_input(node):
        return node

    # Check if it's a label pointing to a file input
    if node.attributes is not None and node.attributes.tag_name == "label" and node.attributes.label_for:
        input_id = node.attributes.label_for
        root_element = get_root(node)

        target_input = find_element_by_id(root_element, input_id)
        if target_input and is_file_input(target_input):
            return target_input

    # Recursively check children
    child_result = find_file_input_recursive(node)
    if child_result:
        return child_result

    # Check siblings
    if node.parent:
        for sibling in node.parent.children:
            if sibling.attributes is not None:
                if is_file_input(sibling):
                    return sibling
    return None
