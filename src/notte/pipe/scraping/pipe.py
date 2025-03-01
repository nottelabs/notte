from enum import StrEnum
from typing import final

from loguru import logger
from pydantic import BaseModel

from notte.browser.processed_snapshot import ProcessedBrowserSnapshot
from notte.browser.window import BrowserWindow
from notte.data.space import DataSpace
from notte.llms.service import LLMService
from notte.pipe.rendering.pipe import DomNodeRenderingConfig, DomNodeRenderingType
from notte.pipe.scraping.images import ImageScrapingPipe
from notte.pipe.scraping.llm_scraping import LlmDataScrapingPipe
from notte.pipe.scraping.schema import SchemaScrapingPipe
from notte.pipe.scraping.simple import SimpleScrapingPipe
from notte.sdk.types import ScrapeParams


class ScrapingType(StrEnum):
    SIMPLE = "simple"
    LLM_EXTRACT = "llm_extract"


class ScrapingConfig(BaseModel):
    type: ScrapingType = ScrapingType.LLM_EXTRACT
    rendering: DomNodeRenderingConfig = DomNodeRenderingConfig(
        type=DomNodeRenderingType.MARKDOWN,
        include_ids=False,
        include_text=True,
    )
    # Change this to 7300 for free tier of Groq / Cerbras
    max_tokens: int = 5000
    long_max_tokens: int = 10000

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
        window: BrowserWindow,
        config: ScrapingConfig,
    ) -> None:
        self.llm_pipe = LlmDataScrapingPipe(llmserve=llmserve, config=config.rendering)
        self.schema_pipe = SchemaScrapingPipe(llmserve=llmserve)
        self.image_pipe = ImageScrapingPipe(window=window, verbose=config.rendering.verbose)
        self.config: ScrapingConfig = config

    def get_scraping_type(self, params: ScrapeParams) -> ScrapingType:
        # use_llm has priority over config.type
        if params.use_llm is not None:
            if self.config.rendering.verbose:
                logger.info(f"📄 User override data scraping type: use_llm={params.use_llm}")
            return ScrapingType.LLM_EXTRACT if params.use_llm else ScrapingType.SIMPLE
        # otherwise, use config.type
        if params.requires_schema():
            return ScrapingType.SIMPLE
        return self.config.type

    async def forward(
        self,
        context: ProcessedBrowserSnapshot,
        params: ScrapeParams,
    ) -> DataSpace:
        match self.get_scraping_type(params):
            case ScrapingType.SIMPLE:
                if self.config.rendering.verbose:
                    logger.info("📀 Scraping page with simple scraping pipe")
                data = SimpleScrapingPipe.forward(context, params.scrape_links)
            case ScrapingType.LLM_EXTRACT:
                if self.config.rendering.verbose:
                    logger.info("📀 Scraping page with complex/LLM-based scraping pipe")
                data = self.llm_pipe.forward(
                    context,
                    only_main_content=params.only_main_content,
                    max_tokens=self.config.long_max_tokens,
                )
        if self.config.rendering.verbose:
            logger.info(f"📀 Extracted page as markdown\n: {data.markdown}\n")
        # scrape images if required
        if params.scrape_images:
            if self.config.rendering.verbose:
                logger.info("🏞️ Scraping images with image pipe")
            data.images = await self.image_pipe.forward(context)

        # scrape structured data if required
        if params.requires_schema() and data.markdown is not None:
            if self.config.rendering.verbose:
                logger.info("🎞️ Structuring data with schema pipe")
            data.structured = self.schema_pipe.forward(
                url=context.snapshot.metadata.url,
                document=data.markdown,
                response_format=params.response_format,
                instructions=params.instructions,
                max_tokens=self.config.max_tokens,
                verbose=self.config.rendering.verbose,
            )
        return data

    async def forward_async(
        self,
        context: ProcessedBrowserSnapshot,
        params: ScrapeParams,
    ) -> DataSpace:
        return await self.forward(context, params)
