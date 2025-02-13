from enum import StrEnum
from typing import final

from loguru import logger
from pydantic import BaseModel

from notte.browser.driver import BrowserDriver
from notte.browser.processed_snapshot import ProcessedBrowserSnapshot
from notte.data.space import DataSpace
from notte.llms.service import LLMService
from notte.pipe.rendering.pipe import DomNodeRenderingConfig, DomNodeRenderingType
from notte.pipe.scraping.complex import ComplexScrapingPipe
from notte.pipe.scraping.schema import SchemaScrapingPipe
from notte.pipe.scraping.simple import SimpleScrapingPipe
from notte.sdk.types import ScrapeParams


class ScrapingType(StrEnum):
    SIMPLE = "simple"
    COMPLEX = "complex"


class ScrapingConfig(BaseModel):
    type: ScrapingType = ScrapingType.COMPLEX
    rendering: DomNodeRenderingConfig = DomNodeRenderingConfig(
        type=DomNodeRenderingType.MARKDOWN,
        include_ids=False,
        include_text=True,
    )
    # Change this to 7300 for free tier of Groq / Cerbras
    max_tokens: int = 5000

    def update_rendering(self, params: ScrapeParams) -> DomNodeRenderingConfig:
        # override rendering config based on request
        return self.rendering.model_copy(
            update={
                "include_images": params.scrape_images,
                "include_links": params.scrape_links,
            }
        )


@final
class DataScrapingPipe:
    """
    Data scraping pipe that scrapes data from the page
    """

    def __init__(
        self,
        llmserve: LLMService,
        browser: BrowserDriver,
    ) -> None:
        self.complex_pipe = ComplexScrapingPipe(llmserve=llmserve, browser=browser)
        self.schema_pipe = SchemaScrapingPipe(llmserve=llmserve)

    async def forward(
        self,
        context: ProcessedBrowserSnapshot,
        config: ScrapingConfig,
        params: ScrapeParams,
    ) -> DataSpace:
        match config.type:
            case ScrapingType.SIMPLE:
                logger.info("📀 Scraping page with simple scraping pipe")
                data = SimpleScrapingPipe.forward(context, params.scrape_links)
            case ScrapingType.COMPLEX:
                logger.info("📀 Scraping page with complex/LLM-based scraping pipe")
                data = await self.complex_pipe.forward(
                    context,
                    only_main_content=params.only_main_content,
                    scrape_images=params.scrape_images,
                    config=config.update_rendering(params),
                    max_tokens=config.max_tokens,
                )
        logger.info(f"📄 Extracted page as markdown\n: {data.markdown}\n")
        if params.requires_schema() and data.markdown is not None:
            data.structured = self.schema_pipe.forward(
                url=context.snapshot.metadata.url,
                document=data.markdown,
                response_format=params.response_format,
                instructions=params.instructions,
                max_tokens=config.max_tokens,
            )
        return data

    async def forward_async(
        self,
        context: ProcessedBrowserSnapshot,
        config: ScrapingConfig,
        params: ScrapeParams,
    ) -> DataSpace:
        return await self.forward(context, config, params)
