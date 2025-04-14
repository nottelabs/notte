from enum import StrEnum
from typing import Self, final

from html2text import config
from loguru import logger
from notte_core.browser.snapshot import BrowserSnapshot
from notte_core.common.config import FrozenConfig
from notte_core.data.space import DataSpace
from notte_core.llms.service import LLMService
from notte_sdk.types import ScrapeParams
from typing_extensions import override

from notte_browser.rendering.pipe import DomNodeRenderingConfig, DomNodeRenderingType
from notte_browser.scraping.llm_scraping import LlmDataScrapingPipe
from notte_browser.scraping.schema import SchemaScrapingPipe
from notte_browser.scraping.simple import SimpleScrapingPipe
from notte_browser.window import BrowserWindow


class ScrapingType(StrEnum):
    SIMPLE = "simple"
    LLM_EXTRACT = "llm_extract"


class ScrapingConfig(FrozenConfig):
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
            deep=True,
            update={
                "include_links": params.scrape_links,
            },
        )

    def set_llm_extract(self: Self) -> Self:
        return self.set_type(ScrapingType.LLM_EXTRACT)

    def set_simple(self: Self) -> Self:
        return self.set_type(ScrapingType.SIMPLE)

    def set_rendering(self: Self, value: DomNodeRenderingConfig) -> Self:
        return self._copy_and_validate(rendering=value)

    def set_max_tokens(self: Self, value: int) -> Self:
        return self._copy_and_validate(max_tokens=value)

    def set_long_max_tokens(self: Self, value: int) -> Self:
        return self._copy_and_validate(long_max_tokens=value)

    def set_type(self: Self, value: ScrapingType) -> Self:
        return self._copy_and_validate(type=value)

    @override
    def set_verbose(self: Self) -> Self:
        return self._copy_and_validate(rendering=self.rendering.set_verbose())


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
        snapshot: BrowserSnapshot,
        params: ScrapeParams,
    ) -> DataSpace:
        match self.get_scraping_type(params):
            case ScrapingType.SIMPLE:
                if self.config.rendering.verbose:
                    logger.info("📀 Scraping page with simple scraping pipe")

                # band-aid fix for now: html2text only takes this global config, no args
                # want to keep image, but can't handle nicer conversion when src is base64
                tmp_images_to_alt = config.IMAGES_TO_ALT
                config.IMAGES_TO_ALT = True
                data = SimpleScrapingPipe.forward(snapshot, params.scrape_links)
                config.IMAGES_TO_ALT = tmp_images_to_alt

            case ScrapingType.LLM_EXTRACT:
                if self.config.rendering.verbose:
                    logger.info("📀 Scraping page with complex/LLM-based scraping pipe")
                data = self.llm_pipe.forward(
                    snapshot,
                    only_main_content=params.only_main_content,
                    max_tokens=self.config.long_max_tokens,
                )
        if self.config.rendering.verbose:
            logger.info(f"📀 Extracted page as markdown\n: {data.markdown}\n")

        # scrape structured data if required
        if params.requires_schema() and data.markdown is not None:
            if self.config.rendering.verbose:
                logger.info("🎞️ Structuring data with schema pipe")
            data.structured = self.schema_pipe.forward(
                url=snapshot.metadata.url,
                document=data.markdown,
                response_format=params.response_format,
                instructions=params.instructions,
                max_tokens=self.config.max_tokens,
                verbose=self.config.rendering.verbose,
            )
        return data

    async def forward_async(
        self,
        snapshot: BrowserSnapshot,
        params: ScrapeParams,
    ) -> DataSpace:
        return await self.forward(snapshot, params)
