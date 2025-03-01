from loguru import logger
from patchright.async_api import Locator, Page

from notte.browser.dom_tree import DomNode
from notte.browser.snapshot import BrowserSnapshot
from notte.browser.window import BrowserWindow
from notte.data.space import ImageCategory, ImageData
from notte.errors.processing import InvalidInternalCheckError
from notte.pipe.preprocessing.dom.locate import locale_element
from notte.pipe.resolution.simple_resolution import SimpleActionResolutionPipe
from notte.utils.image import construct_image_url


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


async def resolve_image_conflict(page: Page, node: DomNode, node_id: str) -> Locator | None:
    if not node_id.startswith("F"):
        raise InvalidInternalCheckError(
            url=node.get_url() or "unknown",
            check="Node ID must start with 'F' for image nodes",
            dev_advice="Check the `resolve_image_conflict` method for more information.",
        )
    image_node = node.find(node_id)
    if image_node is None:
        raise InvalidInternalCheckError(
            url=node.get_url() or "unknown",
            check="Node with id {node_id} not found in graph",
            dev_advice="Check the `resolve_image_conflict` method for more information.",
        )
    selectors = SimpleActionResolutionPipe.resolve_selectors(image_node, verbose=False)
    locator = await locale_element(page, selectors)
    if (await locator.count()) == 1:
        return locator

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
        if image.id == node_id:
            return locator
    return None


async def get_image_src(node: DomNode, locator: Locator | None = None) -> str | None:
    # first check dom node
    if node.attributes is not None:
        if node.attributes.src is not None:
            return node.attributes.src
        if node.attributes.href is not None:
            return node.attributes.href
        if node.attributes.data_src is not None:
            return node.attributes.data_src
        if node.attributes.data_srcset is not None:
            return node.attributes.data_srcset

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


class ImageScrapingPipe:
    """
    Data scraping pipe that scrapes images from the page
    """

    def __init__(self, window: BrowserWindow, verbose: bool = False) -> None:
        self._window: BrowserWindow = window
        self.verbose: bool = verbose

    async def forward(self, snapshot: BrowserSnapshot) -> list[ImageData]:
        image_nodes = snapshot.dom_node.image_nodes()
        out_images: list[ImageData] = []
        for node in image_nodes:
            if node.id is not None:
                locator = await resolve_image_conflict(self._window.page, snapshot.dom_node, node.id)
                # if image_src is None:
                #     logger.warning(f"No src attribute found for image node {node.id}")
                #     continue
                category = await classify_image_element(node, locator)
                image_src = await get_image_src(node, locator)

                if locator is None and (category is None or image_src is None):
                    if self.verbose:
                        logger.warning(f"No locator found for image node {node.id}")
                    continue
                out_images.append(
                    ImageData(
                        id=node.id,
                        category=category,
                        # TODO: fill URL from browser session
                        url=(
                            None
                            if image_src is None
                            else construct_image_url(
                                base_page_url=snapshot.metadata.url,
                                image_src=image_src,
                            )
                        ),
                    )
                )
        return out_images
