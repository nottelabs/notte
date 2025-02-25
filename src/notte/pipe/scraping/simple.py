from main_content_extractor import MainContentExtractor

from notte.browser.processed_snapshot import ProcessedBrowserSnapshot
from notte.data.space import DataSpace


class SimpleScrapingPipe:
    """
    Data scraping pipe that scrapes data from the page
    """

    @staticmethod
    def forward(
        context: ProcessedBrowserSnapshot,
        scrape_links: bool,
    ) -> DataSpace:
        markdown: str = MainContentExtractor.extract(  # type: ignore
            html=context.snapshot.html_content,
            output_format="markdown",
            include_links=scrape_links,
        )
        return DataSpace(markdown=markdown)
