from typing import final

from html2text import config as html2text_config
from loguru import logger
from notte_core.browser.snapshot import BrowserSnapshot
from notte_core.common.config import ScrapingType, config
from notte_core.data.space import DataSpace
from notte_core.llms.service import LLMService
from notte_sdk.types import ScrapeParams

from notte_browser.scraping.images import ImageScrapingPipe
from notte_browser.scraping.markdown import (
    MainContentScrapingPipe,
    MarkdownifyScrapingPipe,
)
from notte_browser.scraping.schema import SchemaScrapingPipe
from notte_browser.window import BrowserWindow


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

                return await MarkdownifyScrapingPipe.forward(
                    window,
                    snapshot,
                    scrape_links=params.scrape_links,
                    scrape_images=params.scrape_images,
                    only_main_content=params.only_main_content,
                )

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

        # scrape images if required
        if params.scrape_images:
            if config.verbose:
                logger.trace("🏞️ Scraping images with image pipe")
            images = await self.image_pipe.forward(window, snapshot)

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
