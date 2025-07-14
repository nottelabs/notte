import markdownify  # type: ignore[import]
from main_content_extractor import MainContentExtractor  # type: ignore[import]
from notte_core.browser.snapshot import BrowserSnapshot

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
        return MainContentExtractor.extract(  # type: ignore[attr-defined]
            html=snapshot.html_content,
            output_format=output_format,
            include_links=scrape_links,
        )


class MarkdownifyScrapingPipe:
    """
    Data scraping pipe that scrapes data from the page
    """

    @staticmethod
    async def forward(
        window: BrowserWindow,
        snapshot: BrowserSnapshot,
        only_main_content: bool,
        scrape_links: bool,
        scrape_images: bool,
        include_iframes: bool = True,
    ) -> str:
        strip: list[str] = []
        if not scrape_links:
            strip.append("a")
        if not scrape_images:
            strip.append("img")

        if only_main_content:
            html = MainContentScrapingPipe.forward(snapshot, scrape_links=scrape_links, output_format="html")
        else:
            html = snapshot.html_content

        content: str = markdownify.markdownify(html, strip=strip)  # type: ignore[attr-defined]

        # manually append iframe text into the content so it's readable by the LLM (includes cross-origin iframes)
        if include_iframes:
            for iframe in window.page.frames:
                if iframe.url != window.page.url and not iframe.url.startswith("data:"):
                    content += f"\n\nIFRAME {iframe.url}:\n"  # type: ignore[attr-defined]
                    content += markdownify.markdownify(await iframe.content())  # type: ignore[attr-defined]

        return content  # type: ignore[return-value]
