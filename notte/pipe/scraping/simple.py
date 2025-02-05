from main_content_extractor import MainContentExtractor

from notte.browser.processed_snapshot import ProcessedBrowserSnapshot
from notte.data.space import DataSpace
from notte.pipe.scraping.config import ScrapingConfig


class SimpleScrapingPipe:
    """
    Data scraping pipe that scrapes data from the page
    """

    @staticmethod
    async def forward(
        context: ProcessedBrowserSnapshot,
        config: ScrapingConfig,
    ) -> DataSpace:
        markdown: str = MainContentExtractor.extract(  # type: ignore
            html=context.snapshot.html_content,
            output_format="markdown",
            include_links=config.params.scrape_links,
        )
        return DataSpace(markdown=markdown)
