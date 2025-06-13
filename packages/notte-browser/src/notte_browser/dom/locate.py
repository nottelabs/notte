from loguru import logger
from notte_core.browser.dom_tree import DomNode, NodeSelectors
from patchright.async_api import FrameLocator, Locator, Page


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

    # playwright selectors cant go through shadow / iframe for now anyway
    if selectors.playwright_selector is not None:
        return frame.locator(selectors.playwright_selector)

    if selectors.in_iframe:
        frame = await locale_element_in_iframes(page, selectors)
    # regular case, locate element + scroll into view if needed

    for selector in [f"css={selectors.css_selector}", f"xpath={selectors.xpath_selector}"]:
        locator = frame.locator(selector)
        count = await locator.count()
        if count > 1:
            logger.debug(f"Found {count} elements for '{selector}'. Check out the dom tree for more details.")
        elif count == 1:
            return locator
    raise ValueError(
        f"No locator is available for xpath='{selectors.xpath_selector}' or css='{selectors.css_selector}'"
    )


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
    )
