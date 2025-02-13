from loguru import logger
from patchright.async_api import Locator, Page

from notte.browser.dom_tree import DomNode
from notte.browser.driver import BrowserDriver
from notte.browser.processed_snapshot import ProcessedBrowserSnapshot
from notte.data.space import DataSpace, ImageCategory, ImageData
from notte.errors.llm import LLMnoOutputCompletionError
from notte.errors.processing import InvalidInternalCheckError
from notte.llms.engine import StructuredContent
from notte.llms.service import LLMService
from notte.pipe.preprocessing.a11y.pipe import A11yPreprocessingPipe
from notte.pipe.rendering.pipe import DomNodeRenderingConfig, DomNodeRenderingPipe
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


class ComplexScrapingPipe:
    """
    Data scraping pipe that scrapes data from the page
    """

    def __init__(self, llmserve: LLMService, browser: BrowserDriver) -> None:
        self.llmserve: LLMService = llmserve
        self.browser: BrowserDriver = browser

    def _render_node(
        self,
        context: ProcessedBrowserSnapshot,
        config: DomNodeRenderingConfig,
        max_tokens: int,
    ) -> str:
        # TODO: add DIVID & CONQUER once this is implemented
        document = DomNodeRenderingPipe.forward(
            node=context.node,
            config=config,
        )
        if len(self.llmserve.tokenizer.encode(document)) <= max_tokens:
            return document
        # too many tokens, use simple AXT
        logger.warning(
            "Document too long for data extraction: "
            f" {len(self.llmserve.tokenizer.encode(document))} tokens => use Simple AXT instead"
        )
        short_snapshot = A11yPreprocessingPipe.forward(context.snapshot, tree_type="simple")
        document = DomNodeRenderingPipe.forward(
            node=short_snapshot.node,
            config=config,
        )
        return document

    async def forward(
        self,
        context: ProcessedBrowserSnapshot,
        only_main_content: bool,
        scrape_images: bool,
        config: DomNodeRenderingConfig,
        max_tokens: int,
    ) -> DataSpace:

        document = self._render_node(context, config, max_tokens)
        # make LLM call
        prompt = "only_main_content" if only_main_content else "all_data"
        response = self.llmserve.completion(prompt_id=f"data-extraction/{prompt}", variables={"document": document})
        if response.choices[0].message.content is None:  # type: ignore
            raise LLMnoOutputCompletionError()
        response_text = str(response.choices[0].message.content)  # type: ignore
        # logger.debug(f"ℹ️ response text: {response_text}")
        sc = StructuredContent(
            outer_tag="data-extraction",
            inner_tag="markdown",
            fail_if_final_tag=False,
            fail_if_inner_tag=False,
        )
        text = sc.extract(response_text)
        return DataSpace(
            markdown=text,
            images=None if not scrape_images else await self._scrape_images(context),
            structured=None,
        )

    async def _scrape_images(self, context: ProcessedBrowserSnapshot) -> list[ImageData]:
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
                                base_page_url=context.snapshot.metadata.url,
                                image_src=image_src,
                            )
                        ),
                    )
                )
        return out_images
