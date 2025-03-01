from main_content_extractor import MainContentExtractor  # type: ignore[import]

from notte.browser.snapshot import BrowserSnapshot
from notte.data.space import DataSpace


class SimpleScrapingPipe:
    """
    Data scraping pipe that scrapes data from the page
    """

    @staticmethod
    def forward(
        snapshot: BrowserSnapshot,
        scrape_links: bool,
    ) -> DataSpace:
        markdown: str = MainContentExtractor.extract(  # type: ignore[attr-defined]
            html=snapshot.html_content,
            output_format="markdown",
            include_links=scrape_links,
        )
        return DataSpace(markdown=markdown)  # type: ignore[arg-type]
