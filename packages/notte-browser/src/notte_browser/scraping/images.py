from bs4 import BeautifulSoup, Tag
from notte_core.common.logging import logger
from notte_core.data.space import ImageCategory, ImageData
from notte_core.utils.image import construct_image_url

from notte_browser.playwright_async_api import Locator
from notte_browser.window import BrowserWindow


async def classify_image_from_tag(
    tag_name: str, locator: Locator | None, has_src: bool = False
) -> ImageCategory | None:
    """Classify an image element based on its tag name and locator.

    Args:
        tag_name: The HTML tag name (img, svg, figure)
        locator: Playwright locator for the image/svg element
        has_src: Whether the element has a valid image source URL

    Returns:
        ImageCategory classification or None
    """
    if tag_name == "svg":
        if locator is None:
            # Fallback: if we have content but no locator, assume SVG content
            return ImageCategory.SVG_CONTENT if has_src else None
        return await classify_svg(locator)
    elif tag_name == "img":
        if locator is None:
            # Fallback: if we have a src but no locator, assume content image
            return ImageCategory.CONTENT_IMAGE if has_src else None
        return await classify_raster_image(locator)
    elif tag_name == "figure":
        return ImageCategory.CONTENT_IMAGE
    return None


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


def get_image_src_from_tag(element: Tag) -> str | None:
    """Extract image source from a BeautifulSoup Tag element."""
    # Try different common image source attributes (including lazy-loaded variants)
    for attr in ["src", "data-src", "srcset", "data-srcset"]:
        src = element.get(attr)
        if src:
            # srcset/data-srcset may be a list, take the first item
            if isinstance(src, list):
                src = src[0] if src else None
            if src:
                # For srcset-style values, take just the URL (first part before space)
                if " " in src:
                    src = src.split()[0]
                return src
    return None


def get_surrounding_text(element: Tag, max_depth: int = 3) -> str | None:
    """Get surrounding text from a BeautifulSoup element by looking at parent/siblings."""
    if max_depth <= 0:
        return None

    # Check for alt text first
    alt = element.get("alt")
    if alt and isinstance(alt, str) and alt.strip():
        return alt.strip()

    # Check aria-label
    aria_label = element.get("aria-label")
    if aria_label and isinstance(aria_label, str) and aria_label.strip():
        return aria_label.strip()

    # Check title attribute
    title = element.get("title")
    if title and isinstance(title, str) and title.strip():
        return title.strip()

    # Try to get text from parent
    parent = element.parent
    if parent is not None and isinstance(parent, Tag):  # pyright: ignore [reportUnnecessaryIsInstance]
        text = parent.get_text(strip=True)
        if text:
            return text[:200]  # Limit description length
        return get_surrounding_text(parent, max_depth - 1)

    return None


async def get_svg_content(locator: Locator | None = None) -> str | None:
    """Get the content of an SVG element."""
    if locator is None:
        return None
    return await locator.evaluate("el => el.outerHTML")


class ImageScrapingPipe:
    """
    Data scraping pipe that scrapes images from the page using BeautifulSoup.
    No longer depends on DOM tree computation.
    """

    def __init__(self, verbose: bool = False) -> None:
        self.verbose: bool = verbose

    async def forward(
        self,
        window: BrowserWindow,
        html_content: str,
        base_url: str,
    ) -> list[ImageData]:
        """
        Extract images from HTML content using BeautifulSoup.

        Args:
            window: BrowserWindow for Playwright locator access (for classification)
            html_content: The raw HTML content to parse
            base_url: The base URL for constructing absolute image URLs
        """
        from notte_core.utils.url import clean_url

        soup = BeautifulSoup(html_content, "html.parser")

        # Find all img, svg, and figure elements
        image_elements = soup.find_all(["img", "svg", "figure"])

        out_images: list[ImageData] = [
            # first image is the favicon
            ImageData(
                category=ImageCategory.FAVICON,
                url=f"{base_url}/favicon.ico",
                description=f"Favicon for {clean_url(base_url)}",
            )
        ]

        # Get all Playwright locators for images and SVGs for classification
        img_locators = await window.page.locator("img").all()
        svg_locators = await window.page.locator("svg").all()

        img_idx = 0
        svg_idx = 0

        # Only use tqdm progress bar when verbose
        if self.verbose:
            from tqdm import tqdm

            elements_iter = tqdm(image_elements)
        else:
            elements_iter = image_elements

        for element in elements_iter:
            if not isinstance(element, Tag):  # pyright: ignore [reportUnnecessaryIsInstance]
                continue

            tag_name = element.name
            locator: Locator | None = None

            # Match element to Playwright locator by index
            if tag_name == "img" and img_idx < len(img_locators):
                locator = img_locators[img_idx]
                img_idx += 1
            elif tag_name == "svg" and svg_idx < len(svg_locators):
                locator = svg_locators[svg_idx]
                svg_idx += 1
            elif tag_name == "figure":
                # Figures don't have Playwright locators, skip index increment
                locator = None

            # Extract image source from HTML attributes
            image_src = get_image_src_from_tag(element)

            # Classify the image element (pass has_src for fallback when locator is None)
            category = await classify_image_from_tag(tag_name, locator, has_src=image_src is not None)

            # Construct absolute URL
            if image_src is not None:
                if len(image_src) > 0 and image_src != base_url:
                    image_src = construct_image_url(
                        base_page_url=base_url,
                        image_src=image_src,
                    )
                    if image_src == base_url:
                        # Reset if it's the same as page URL
                        image_src = None
                else:
                    image_src = None

            # For SVG content, get the actual SVG markup
            if image_src is None and category == ImageCategory.SVG_CONTENT:
                image_src = await get_svg_content(locator)

            # Skip if we couldn't get useful data
            if locator is None and (category is None or image_src is None):
                if self.verbose:
                    logger.debug("Skipping image element: no locator and missing category/src")
                continue

            out_images.append(
                ImageData(
                    category=category,
                    url=image_src,
                    description=get_surrounding_text(element),
                )
            )

        return out_images
