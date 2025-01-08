from loguru import logger
from playwright.async_api import Locator, Page
from tiktoken import encoding_for_model
from typing_extensions import final

from notte.browser.context import Context
from notte.browser.driver import BrowserDriver
from notte.browser.node_type import NotteNode
from notte.browser.observation import DataSpace, ImageCategory, ImageData
from notte.llms.engine import StructuredContent
from notte.llms.service import LLMService
from notte.pipe.preprocessing.a11y.tree import ProcessedA11yTree
from notte.utils.image import construct_image_url


async def classify_image_element(locator: Locator) -> ImageCategory:
    """Classify an image or SVG element.

    Args:
        locator: Playwright locator for the image/svg element

    Returns:
        tuple[ImageType, str | None]: Element classification and source/content
    """
    # First check if it's an SVG
    tag_name = await locator.evaluate("el => el.tagName.toLowerCase()")

    if tag_name == "svg":
        return await classify_svg(locator)
    else:
        return await classify_raster_image(locator)


async def classify_svg(locator: Locator, return_svg_content: bool = False) -> ImageCategory:
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
    dimensions = await locator.evaluate(
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


async def resolve_image_conflict(page: Page, node: NotteNode, node_id: str) -> Locator | None:
    if not node_id.startswith("F"):
        raise ValueError("Node ID must start with 'F' for image nodes")
    image_node = node.find(node_id)
    if image_node is None:
        raise ValueError(f"Node with id {node_id} not found in graph")
    if len(image_node.text) > 0:
        locators = await page.get_by_role(image_node.get_role_str(), name=image_node.text).all()  # type: ignore
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


async def get_image_src(locator: Locator) -> str | None:
    # Try different common image source attributes
    for attr in ["src", "data-src", "srcset"]:
        src = await locator.get_attribute(attr)
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


@final
class DataScrapingPipe:

    def __init__(self, llmserve: LLMService | None = None, browser: BrowserDriver | None = None) -> None:
        self.llmserve: LLMService = llmserve or LLMService()
        self.browser: BrowserDriver | None = browser
        self.token_encoder = encoding_for_model("gpt-4o")
        self.max_tokens = 7300

    async def forward(self, context: Context, scrape_images: bool = True) -> DataSpace:
        # TODO: add DIVID & CONQUER once this is implemented
        document = context.markdown_description(include_ids=False, include_images=scrape_images)
        if len(self.token_encoder.encode(document)) > self.max_tokens:
            logger.warning(
                (
                    "Document too long for data extraction: "
                    f" {len(self.token_encoder.encode(document))} tokens => use Simple AXT instead"
                )
            )
            tree = ProcessedA11yTree.from_a11y_tree(context.snapshot.a11y_tree)
            simple_node = NotteNode.from_a11y_node(tree.simple_tree, path=context.snapshot.url)
            document = Context.format(simple_node, include_ids=False)

        # make LLM call
        response = self.llmserve.completion(prompt_id="data-extraction/optim", variables={"document": document})
        sc = StructuredContent(outer_tag="data-extraction", inner_tag="markdown")
        if response.choices[0].message.content is None:  # type: ignore
            raise ValueError("No content in response")
        response_text = str(response.choices[0].message.content)  # type: ignore
        text = sc.extract(
            response_text,
            fail_if_final_tag=False,
            fail_if_inner_tag=False,
        )
        return DataSpace(
            markdown=text,
            images=None if not scrape_images else await self._scrape_images(context),
            structured=None,
        )

    async def _scrape_images(self, context: Context) -> list[ImageData]:
        if self.browser is None:
            logger.error("Images cannot be scraped without a browser")
            return []
        image_nodes = context.node.image_nodes()
        out_images: list[ImageData] = []
        for node in image_nodes:
            if node.id is not None:
                locator = await resolve_image_conflict(self.browser.page, context.node, node.id)
                if locator is None:
                    logger.warning(f"No locator found for image node {node.id}")
                    continue
                # if image_src is None:
                #     logger.warning(f"No src attribute found for image node {node.id}")
                #     continue
                category = await classify_image_element(locator)
                image_src = await get_image_src(locator)
                out_images.append(
                    ImageData(
                        id=node.id,
                        category=category,
                        # TODO: fill URL from browser session
                        url=(
                            None
                            if image_src is None
                            else construct_image_url(
                                base_page_url=context.snapshot.url,
                                image_src=image_src,
                            )
                        ),
                    )
                )
        return out_images

    async def forward_async(self, context: Context, scrape_images: bool = True) -> DataSpace:
        return await self.forward(context, scrape_images=scrape_images)
