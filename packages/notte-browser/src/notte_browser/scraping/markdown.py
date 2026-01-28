from typing import Any

from bs4 import BeautifulSoup
from main_content_extractor import MainContentExtractor  # type: ignore[import]
from markdownify import MarkdownConverter  # pyright: ignore [reportMissingTypeStubs]
from notte_core.browser.snapshot import BrowserSnapshot
from notte_core.common.logging import logger
from notte_sdk.types import ScrapeParams
from typing_extensions import override

from notte_browser.errors import EmptyPageContentError, PlaywrightError
from notte_browser.window import BrowserWindow


class MainContentScrapingPipe:
    """
    Data scraping pipe that scrapes data from the page
    """

    @staticmethod
    def forward(
        snapshot: BrowserSnapshot,
        scrape_links: bool,
        output_format: str = "markdown",
    ) -> str:
        data = MainContentExtractor.extract(  # type: ignore[attr-defined]
            html=snapshot.html_content,
            output_format=output_format,
            include_links=scrape_links,
        )
        if data is None or not isinstance(data, str) or len(data) == 0:
            raise EmptyPageContentError(url=snapshot.metadata.url, nb_retries=1)
        return data


class VisibleMarkdownConverter(MarkdownConverter):
    """Ignore hidden content on the page"""

    @override
    def convert_soup(self, soup: BeautifulSoup) -> str | Any:
        # Remove hidden elements before conversion
        for element in soup.find_all(style=True):
            if not hasattr(element, "attrs") or element.attrs is None:  # pyright: ignore [reportUnnecessaryComparison]
                continue

            style = element.get("style", "")
            if "display:none" in style.replace(" ", "") or "visibility:hidden" in style.replace(" ", ""):  # pyright: ignore [reportUnknownMemberType, reportOptionalMemberAccess, reportAttributeAccessIssue]
                element.decompose()

        return super().convert_soup(soup)  # pyright: ignore [reportUnknownVariableType, reportUnknownMemberType]


class MarkdownifyScrapingPipe:
    """
    Data scraping pipe that scrapes data from the page
    """

    @staticmethod
    async def forward(
        window: BrowserWindow,
        snapshot: BrowserSnapshot,
        params: ScrapeParams,
        include_iframes: bool | None = None,
    ) -> str:
        if params.only_main_content:
            html = MainContentScrapingPipe.forward(snapshot, scrape_links=params.scrape_links, output_format="html")

        else:
            html = snapshot.html_content
        converter = VisibleMarkdownConverter(strip=params.removed_tags())
        content: str = converter.convert(html)  # type: ignore[attr-defined]

        # manually append iframe text into the content so it's readable by the LLM (includes cross-origin iframes)
        # don't include iframes by default if a selector is set (scraping specific element)
        if include_iframes is None:
            include_iframes = params.selector is None

        if include_iframes:
            for iframe in window.page.frames:
                if iframe.url != window.page.url and not iframe.url.startswith("data:"):
                    try:
                        iframe_content = await iframe.content()
                        content += f"\n\nIFRAME {iframe.url}:\n"  # type: ignore[attr-defined]
                        content += converter.convert(iframe_content)  # type: ignore[attr-defined]
                    except PlaywrightError as e:
                        logger.warning(f"Failed to get iframe content for {iframe.url}: {e}")

        return content  # type: ignore[return-value]
