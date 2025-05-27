import markdownify  # type: ignore[import]
from main_content_extractor import MainContentExtractor  # type: ignore[import]
from notte_core.browser.snapshot import BrowserSnapshot
from notte_core.errors.llm import LLMnoOutputCompletionError
from notte_core.llms.engine import StructuredContent
from notte_core.llms.service import LLMService

from notte_browser.rendering.pipe import DomNodeRenderingPipe, DomNodeRenderingType
from notte_browser.scraping.pruning import MarkdownPruningPipe
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


class Llm2MarkdownScrapingPipe:
    """
    Data scraping pipe that scrapes data from the page
    """

    def __init__(self, llmserve: LLMService) -> None:
        self.llmserve: LLMService = llmserve

    def _render_node(
        self,
        snapshot: BrowserSnapshot,
    ) -> str:
        # TODO: add DIVID & CONQUER once this is implemented
        document = DomNodeRenderingPipe.forward(
            node=snapshot.dom_node, type=DomNodeRenderingType.MARKDOWN, include_ids=False
        )
        document = self.llmserve.clip_tokens(document)
        return document

    def forward(
        self,
        snapshot: BrowserSnapshot,
        only_main_content: bool,
        use_link_placeholders: bool = True,
    ) -> str:
        document = self._render_node(snapshot)
        masked_document = MarkdownPruningPipe.mask(document)
        if use_link_placeholders:
            document = masked_document.content
        # make LLM call
        prompt = "only_main_content" if only_main_content else "all_data"
        response = self.llmserve.completion(prompt_id=f"data-extraction/{prompt}", variables={"document": document})
        if response.choices[0].message.content is None:  # type: ignore[arg-type]
            raise LLMnoOutputCompletionError()
        response_text = str(response.choices[0].message.content)  # type: ignore[arg-type]
        if use_link_placeholders:
            response_text = MarkdownPruningPipe.unmask(masked_document.with_content(response_text))
        sc = StructuredContent(
            outer_tag="data-extraction",
            inner_tag="markdown",
            fail_if_final_tag=False,
            fail_if_inner_tag=False,
        )
        return sc.extract(response_text)
