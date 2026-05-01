import re
from typing import final

from html2text import config as html2text_config
from notte_core.browser.snapshot import BrowserSnapshot
from notte_core.common.config import ScrapingType, config
from notte_core.common.logging import logger
from notte_core.data.space import DataSpace
from notte_llm.service import LLMService
from notte_sdk.types import ScrapeParams

from notte_browser.scraping.images import ImageScrapingPipe
from notte_browser.scraping.markdown import (
    MainContentScrapingPipe,
    MarkdownifyScrapingPipe,
)
from notte_browser.scraping.pruning import MarkdownPruningPipe
from notte_browser.scraping.schema import SchemaScrapingPipe
from notte_browser.window import BrowserWindow


def _calculate_url_percentage(text: str) -> float:
    """
    Calculate the percentage of text that consists of URLs.

    Uses the formula: (len(text) - len(text_without_urls)) / len(text)

    Uses the same patterns as MarkdownPruningPipe to ensure consistency.

    Detects URLs in:
    - Markdown links: [text](url)
    - Markdown images: ![alt](url)

    Returns:
        Percentage (0.0 to 1.0) of text that is URLs
    """
    if not text:
        return 0.0

    total_length = len(text)
    text_without_urls = text

    # Remove URLs from markdown images: ![alt](url) -> ![alt]()
    # Uses MarkdownPruningPipe.image_pattern to ensure consistency
    def remove_image_url(match: re.Match[str]) -> str:
        alt_text, _url = match.groups()
        return f"![{alt_text}]()"

    text_without_urls = re.sub(MarkdownPruningPipe.image_pattern, remove_image_url, text_without_urls)

    # Remove URLs from markdown links: [text](url) -> [text]()
    # Uses MarkdownPruningPipe.link_pattern to ensure consistency
    def remove_link_url(match: re.Match[str]) -> str:
        link_text, _url = match.groups()
        return f"[{link_text}]()"

    text_without_urls = re.sub(MarkdownPruningPipe.link_pattern, remove_link_url, text_without_urls)

    # Calculate percentage: (original - without_urls) / original
    url_length = total_length - len(text_without_urls)
    return url_length / total_length if total_length > 0 else 0.0


@final
class DataScrapingPipe:
    """
    Data scraping pipe that scrapes data from the page
    """

    def __init__(
        self,
        llmserve: LLMService,
        type: ScrapingType,
    ) -> None:
        self.schema_pipe = SchemaScrapingPipe(llmserve=llmserve)
        self.image_pipe = ImageScrapingPipe(verbose=config.verbose)
        self.scraping_type = type

    def get_markdown_scraping_type(self, params: ScrapeParams) -> ScrapingType:
        # otherwise, use config.type
        if params.requires_schema():
            return ScrapingType.MARKDOWNIFY
        return self.scraping_type

    async def scrape_markdown(self, window: BrowserWindow, snapshot: BrowserSnapshot, params: ScrapeParams) -> str:
        match self.get_markdown_scraping_type(params):
            case ScrapingType.MARKDOWNIFY:
                if config.verbose:
                    logger.trace("📀 Scraping page with simple scraping pipe")

                return await MarkdownifyScrapingPipe.forward(window, snapshot, params)

            case ScrapingType.MAIN_CONTENT:
                if config.verbose:
                    logger.trace("📀 Scraping page with main content scraping pipe")
                if not params.only_main_content:
                    raise ValueError("Main content scraping pipe only supports only_main_content=True")
                # band-aid fix for now: html2text only takes this global config, no args
                # want to keep image, but can't handle nicer conversion when src is base64
                tmp_images_to_alt = html2text_config.IMAGES_TO_ALT
                html2text_config.IMAGES_TO_ALT = True
                data = MainContentScrapingPipe.forward(snapshot, params.scrape_links)
                html2text_config.IMAGES_TO_ALT = tmp_images_to_alt
                return data

    async def forward(
        self,
        window: BrowserWindow,
        snapshot: BrowserSnapshot,
        params: ScrapeParams,
    ) -> DataSpace:
        markdown = await self.scrape_markdown(window, snapshot, params)
        if config.verbose:
            logger.trace(f"📀 Extracted page as markdown\n: {markdown}\n")
        images = None
        structured = None

        # Warn if processing very large text (>= 100k chars)
        if params.requires_schema() and len(markdown) >= 100000:
            logger.warning(
                (
                    f"You are processing a large text input ({len(markdown):,} characters, >= 100k). "
                    "Consider using a combination of `only_main_content=True`, `use_link_placeholders=True`, "
                    'or `selector="<your-selector>"` to speed up processing and/or manage your token cost.'
                )
            )

        # Warn if URLs account for >= 50% of text and user should consider using placeholders
        # Only show warning for text longer than 10k chars (meaningful for larger content)
        if params.requires_schema() and not params.use_link_placeholders and len(markdown) > 10000:
            url_percentage = _calculate_url_percentage(markdown)
            if url_percentage >= 0.5:
                logger.warning(
                    (
                        f"URLs account for {url_percentage:.1%} of your scraped content. "
                        "Consider using `use_link_placeholders=True` to reduce token usage and improve LLM performance. "
                    )
                )

        # Apply link placeholders to markdown if requested (even without schema)
        # WARNING: This is not recommended as placeholders are meant for LLM processing
        # and unmasking only happens during structured data extraction
        if params.use_link_placeholders and not params.requires_schema():
            logger.warning(
                (
                    "use_link_placeholders=True without schema extraction (response_format/instructions) is not recommended. "
                    "Placeholders are designed for LLM processing and will not be unmasked in the returned markdown."
                )
            )
            masked_document = MarkdownPruningPipe.mask(markdown)
            markdown = masked_document.content

        # scrape images if required
        if params.only_images:
            if config.verbose:
                logger.trace("🏞️ Scraping images with image pipe")
            images = await self.image_pipe.forward(
                window,
                snapshot.html_content,
                snapshot.metadata.url,
            )

        # scrape structured data if required
        if params.requires_schema():
            if config.verbose:
                logger.trace("🎞️ Structuring data with schema pipe")
            structured = await self.schema_pipe.forward(
                url=snapshot.metadata.url,
                document=markdown,
                response_format=params.response_format,
                instructions=params.instructions,
                verbose=config.verbose,
                use_link_placeholders=params.use_link_placeholders,
            )
        return DataSpace(markdown=markdown, images=images, structured=structured)
