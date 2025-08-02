from loguru import logger
from notte_core.browser.dom_tree import DomNode, InteractionDomNode
from notte_core.browser.node_type import NodeType
from notte_core.browser.snapshot import BrowserSnapshot
from notte_core.data.space import ImageCategory, ImageData
from notte_core.utils.image import construct_image_url

from notte_browser.dom.locate import locate_element
from notte_browser.playwright_async_api import Locator, Page
from notte_browser.resolution import NodeResolutionPipe
from notte_browser.window import BrowserWindow


async def classify_image_element(node: DomNode, locator: Locator | None = None) -> ImageCategory | None:
    """Classify an image or SVG element.

    Args:
        locator: Playwright locator for the image/svg element

    Returns:
        tuple[ImageType, str | None]: Element classification and source/content
    """
    if node.attributes is not None:
        tag_name: str = node.attributes.tag_name
    else:
        if locator is None:
            return None
        # First check if it's an SVG
        tag_name = await locator.evaluate("el => el.tagName.toLowerCase()")

    if tag_name == "svg":
        if locator is None:
            return None
        return await classify_svg(locator)
    else:
        if locator is None:
            return None
        return await classify_raster_image(locator)


async def classify_svg(
    locator: Locator,
    return_svg_content: bool = False,  # type: ignore[unused-argument]
) -> ImageCategory:
    """Classify an SVG element specifically."""
    # Common SVG attributes that might indicate purpose
    role = await locator.get_attribute("role")
    # aria_hidden = await locator.get_attribute("aria-hidden")
    aria_label = await locator.get_attribute("aria-label")
    classes = (await locator.get_attribute("class") or "").lower()

    # Get SVG dimensions
    dimensions = await locator.evaluate(
        """el => {
        const bbox = el.getBBox();
        return {
            width: bbox.width,
            height: bbox.height
        }
    }"""
    )

    # Get SVG content for debugging/identification
    # svg_content = (await locator.evaluate("el => el.outerHTML")) if return_svg_content else None

    # Classify SVG
    width, height = dimensions["width"], dimensions["height"]
    if width is None or height is None:
        return ImageCategory.SVG_CONTENT
    is_likely_icon = (
        width <= 64
        and height <= 64  # Small size
        or "icon" in classes
        or "icon" in (aria_label or "").lower()
        or role == "img"
        and width <= 64  # Small SVG with img role
    )

    if is_likely_icon:
        return ImageCategory.SVG_ICON
    else:
        return ImageCategory.SVG_CONTENT


async def classify_raster_image(locator: Locator) -> ImageCategory:
    """Classify a regular image element."""
    # Get element properties
    role = await locator.get_attribute("role")
    aria_hidden = await locator.get_attribute("aria-hidden")
    aria_label = await locator.get_attribute("aria-label")
    alt = await locator.get_attribute("alt")
    classes = (await locator.get_attribute("class") or "").lower()
    presentation = role == "presentation"

    # Try to get dimensions
    dimensions: dict[str, int | None] = await locator.evaluate(
        """el => {
        return {
            width: el.naturalWidth || el.width,
            height: el.naturalHeight || el.height
        }
    }"""
    )
    width, height = dimensions["width"], dimensions["height"]
    if width is None or height is None:
        return ImageCategory.SVG_CONTENT

    # Check if it's an icon
    if (
        "icon" in classes
        or "icon" in (aria_label or "").lower()
        or "icon" in (alt or "").lower()
        or (width <= 64 and height <= 64)  # Small size
    ):
        return ImageCategory.ICON

    # Check if it's decorative
    if presentation or aria_hidden == "true" or (alt == "" and not aria_label):
        return ImageCategory.DECORATIVE

    return ImageCategory.CONTENT_IMAGE


async def resolve_image_conflict(page: Page, node: DomNode, image_node: InteractionDomNode) -> Locator | None:
    selectors = NodeResolutionPipe.resolve_selectors(image_node, verbose=False)
    try:
        locator = await locate_element(page, selectors)
        if (await locator.count()) == 1:
            return locator
    except Exception as e:
        logger.debug(f"Error locating element: {e}")

    if len(image_node.text) > 0:
        locators = await page.get_by_role(image_node.get_role_str(), name=image_node.text).all()  # type: ignore[arg-type]
        if len(locators) == 1:
            return locators[0]

    # check by comparing the IDX position of the images
    images = node.image_nodes()
    locators = await page.get_by_role("img").all()
    if len(images) != len(locators):
        return None

    for image, locator in zip(images, locators):
        if image == image_node:
            return locator
    return None


async def get_image_src(node: DomNode, locator: Locator | None = None) -> str | None:
    # first check dom node
    if node.attributes is not None:
        resource_url = node.attributes.get_resource_url()
        if resource_url is not None:
            return resource_url

    if locator is None:
        return None
    # Try different common image source attributes
    for attr in ["src", "data-src", "srcset"]:
        src: str | None = await locator.get_attribute(attr)
        if src:
            return src

    # If still no success, try evaluating directly
    src = await locator.evaluate(
        """element => {
        // Get computed src
        return element.currentSrc || element.src || element.getAttribute('data-src');
    }"""
    )

    return src


async def get_svg_content(locator: Locator | None = None) -> str | None:
    """Get the content of an SVG element."""
    if locator is None:
        return None
    return await locator.evaluate("el => el.outerHTML")


async def get_parent_inner_text(dom_node: DomNode, max_depth: int = 3) -> str | None:
    """Get the inner text of an element."""
    if max_depth <= 0:
        return None
    text = dom_node.inner_text()
    if len(text) > 0:
        return text
    # check the parent
    parent = dom_node.parent
    if parent is not None:
        return await get_parent_inner_text(parent, max_depth - 1)
    return None


class ImageScrapingPipe:
    """
    Data scraping pipe that scrapes images from the page
    """

    def __init__(self, verbose: bool = False) -> None:
        self.verbose: bool = verbose

    async def forward(self, window: BrowserWindow, snapshot: BrowserSnapshot) -> list[ImageData]:
        image_nodes = snapshot.dom_node.image_nodes()
        out_images: list[ImageData] = [
            # first image is the favicon
            ImageData(
                category=ImageCategory.FAVICON,
                url=f"{snapshot.metadata.url}/favicon.ico",
                description=f"Favicon for {snapshot.clean_url}",
            )
        ]
        from tqdm import tqdm

        for i, node in tqdm(enumerate(image_nodes)):
            locator = await resolve_image_conflict(
                page=window.page,
                node=snapshot.dom_node,
                image_node=InteractionDomNode(
                    id=node.id or f"image_{i}",
                    type=NodeType.INTERACTION,
                    role=node.role,
                    text=node.text,
                    children=[],
                    attributes=node.attributes,
                    computed_attributes=node.computed_attributes,
                ),
            )
            # if image_src is None:
            #     logger.debug(f"No src attribute found for image node {node.id}")
            #     continue
            category = await classify_image_element(node, locator)
            image_src = await get_image_src(node, locator)
            if image_src is not None:
                if len(image_src) > 0 and image_src != snapshot.metadata.url:
                    original_url = image_src
                    image_src = construct_image_url(
                        base_page_url=snapshot.metadata.url,
                        image_src=image_src,
                    )
                    if image_src == snapshot.metadata.url:
                        raise ValueError(
                            f"Image src is the same as the page url for image node {node.id} but original url is {original_url}"
                        )
                else:
                    # manually reset the image_src to None if it's empty
                    # or the same as the page url (likely just a href)
                    image_src = None
            if image_src is None and category is ImageCategory.SVG_CONTENT:
                image_src = await get_svg_content(locator)

            if locator is None and (category is None or image_src is None):
                if self.verbose:
                    logger.debug(f"No locator found for image node {node.id}")
                continue
            out_images.append(
                ImageData(
                    category=category,
                    url=image_src,
                    description=await get_parent_inner_text(node),
                )
            )
        return out_images
