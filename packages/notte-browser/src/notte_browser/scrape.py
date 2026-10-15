# pyright: reportPrivateUsage=false, reportUnknownMemberType=false

import asyncio
import re
from typing import Any, Callable, cast

import html2text
from bs4 import BeautifulSoup
from lxml import etree
from lxml import html as lxml_html
from markdownify import MarkdownConverter
from notte_core.config import config
from notte_core.data import DataSpace
from notte_core.extraction import StructuredExtractor
from notte_core.logging import logger
from notte_core.profiling import profiler
from notte_core.pruning import IMAGE_PATTERN, LINK_PATTERN, mask_markdown
from notte_core.snapshot import BrowserSnapshot
from notte_core.types import ScrapeParams
from typing_extensions import override

from notte_browser.driver import Frame
from notte_browser.errors import EmptyPageContentError, PlaywrightError, StructuredExtractorNotAvailableError
from notte_browser.js import script
from notte_browser.window import BrowserWindow


async def scrape_page(
    window: BrowserWindow,
    params: ScrapeParams,
    *,
    get_extractor: Callable[[], StructuredExtractor],
    retries: int = 3,
    wait_time: int = 2000,
) -> DataSpace:
    try:
        return await scrape_snapshot(
            window=window,
            # scrapes only read the html: skip the dom tree and the screenshot
            snapshot=await window.snapshot(selector=params.selector, skip_dom=True, screenshot=False),
            params=params,
            get_extractor=get_extractor,
        )
    except EmptyPageContentError as e:
        if retries == 0:
            raise e
        logger.warning(f"Scrape failed after empty page content, retrying in {wait_time / 1000} seconds...")
        await asyncio.sleep(wait_time / 1000)
        async with profiler.profile("NotteSession._ascrape", service_name="execution"):
            return await scrape_page(
                window, params, get_extractor=get_extractor, retries=retries - 1, wait_time=wait_time
            )


async def scrape_snapshot(
    window: BrowserWindow,
    snapshot: BrowserSnapshot,
    params: ScrapeParams,
    *,
    get_extractor: Callable[[], StructuredExtractor],
) -> DataSpace:
    markdown = await page_markdown(window, snapshot, params)
    if config.verbose:
        logger.trace(f"📀 Extracted page as markdown\n: {markdown}\n")
    structured = None

    # Warn if processing very large text (>= 100k chars)
    if params.requires_schema() and len(markdown) >= 100000:
        logger.warning(
            (
                f"You are processing a large text input ({len(markdown):,} characters, >= 100k). "
                "Consider using a combination of `only_main_content=True`, `use_link_placeholders=True`, "
                'or `selector="<your-selector>"` to speed up processing and/or manage your token cost.'
            )
        )

    # Warn if URLs account for >= 50% of text and user should consider using placeholders
    # Only show warning for text longer than 10k chars (meaningful for larger content)
    if params.requires_schema() and not params.use_link_placeholders and len(markdown) > 10000:
        url_percentage = _calculate_url_percentage(markdown)
        if url_percentage >= 0.5:
            logger.warning(
                (
                    f"URLs account for {url_percentage:.1%} of your scraped content. "
                    "Consider using `use_link_placeholders=True` to reduce token usage and improve LLM performance. "
                )
            )

    # Apply link placeholders to markdown if requested (even without schema)
    # WARNING: This is not recommended as placeholders are meant for LLM processing
    # and unmasking only happens during structured data extraction
    if params.use_link_placeholders and not params.requires_schema():
        logger.warning(
            (
                "use_link_placeholders=True without schema extraction (response_format/instructions) is not recommended. "
                "Placeholders are designed for LLM processing and will not be unmasked in the returned markdown."
            )
        )
        masked_document = mask_markdown(markdown)
        markdown = masked_document.content

    # scrape structured data if required
    if params.requires_schema():
        if config.verbose:
            logger.trace("🎞️ Structuring data with schema pipe")
        structured = await get_extractor().extract(
            url=snapshot.metadata.url,
            document=markdown,
            response_format=params.response_format,
            instructions=params.instructions,
            model=params.model,
            use_link_placeholders=params.use_link_placeholders,
        )
    return DataSpace(markdown=markdown, structured=structured)


def default_extractor() -> StructuredExtractor:
    """The LLM extractor from the optional `notte-llm` package, when it is installed."""
    try:
        from notte_llm import LlmExtractor
    except ImportError as e:
        raise StructuredExtractorNotAvailableError() from e
    return LlmExtractor()


def _calculate_url_percentage(text: str) -> float:
    """
    Calculate the percentage of text that consists of URLs.

    Uses the formula: (len(text) - len(text_without_urls)) / len(text)

    Uses the same patterns as markdown pruning to ensure consistency.

    Detects URLs in:
    - Markdown links: [text](url)
    - Markdown images: ![alt](url)

    Returns:
        Percentage (0.0 to 1.0) of text that is URLs
    """
    if not text:
        return 0.0

    total_length = len(text)
    text_without_urls = text

    # Remove URLs from markdown images: ![alt](url) -> ![alt]()
    # Uses IMAGE_PATTERN to ensure consistency
    def remove_image_url(match: re.Match[str]) -> str:
        alt_text, _url = match.groups()
        return f"![{alt_text}]()"

    text_without_urls = re.sub(IMAGE_PATTERN, remove_image_url, text_without_urls)

    # Remove URLs from markdown links: [text](url) -> [text]()
    # Uses LINK_PATTERN to ensure consistency
    def remove_link_url(match: re.Match[str]) -> str:
        link_text, _url = match.groups()
        return f"[{link_text}]()"

    text_without_urls = re.sub(LINK_PATTERN, remove_link_url, text_without_urls)

    # Calculate percentage: (original - without_urls) / original
    url_length = total_length - len(text_without_urls)
    return url_length / total_length if total_length > 0 else 0.0


_MAIN_CONTENT_REMOVED_TAGS = ("script", "style", "aside", "footer", "header", "hgroup", "nav", "search")


def _remove_subtree(element: etree._Element) -> None:
    parent = element.getparent()
    if parent is None:
        return
    if element.tail:
        previous = element.getprevious()
        if previous is None:
            parent.text = (parent.text or "") + element.tail
        else:
            previous.tail = (previous.tail or "") + element.tail
    parent.remove(element)


def _unwrap_element(element: etree._Element) -> None:
    parent = element.getparent()
    if parent is None:
        return

    previous = element.getprevious()
    if element.text:
        if previous is None:
            parent.text = (parent.text or "") + element.text
        else:
            previous.tail = (previous.tail or "") + element.text

    index = parent.index(element)
    children = list(element)
    for child in children:
        element.remove(child)
        parent.insert(index, child)
        index += 1

    if element.tail:
        tail_target = children[-1] if children else previous
        if tail_target is None:
            parent.text = (parent.text or "") + element.tail
        else:
            tail_target.tail = (tail_target.tail or "") + element.tail
    parent.remove(element)


def _hides(style: str) -> bool:
    """Whether an inline `style` hides its element."""
    style = style.replace(" ", "")
    return "display:none" in style or "visibility:hidden" in style


def _remove_hidden_elements(root: etree._Element) -> None:
    for element in list(root.iter()):
        if _hides(str(element.get("style", "")).lower()):
            _remove_subtree(element)


def _strip_configured_tags(elements: list[etree._Element], tags: list[str]) -> None:
    normalized_tags = {tag.lower() for tag in tags}
    for root in elements:
        for element in list(root.iterdescendants()):
            tag = cast(object, element.tag)
            if not isinstance(tag, str):
                continue
            normalized_tag = tag.lower()
            if normalized_tag not in normalized_tags:
                continue
            if normalized_tag == "img":
                _remove_subtree(element)
            else:
                _unwrap_element(element)


def _deepest_content_id(root: etree._Element) -> etree._Element | None:
    matches = [element for element in root.iter() if element.get("id") in {"contents", "main"}]
    if not matches:
        return None
    return max(matches, key=lambda element: sum(1 for _ in element.iterancestors()))


def _trafilatura_fallback(html: str) -> list[etree._Element]:
    # Imported here: trafilatura is slow to import and only needed when a page has no recognisable main content.
    import trafilatura

    extracted = trafilatura.extract(
        html,
        output_format="xml",
        include_tables=True,
        include_images=True,
        include_links=True,
    )
    if not extracted:
        return []

    root = etree.fromstring(extracted.encode("utf-8"))
    for element in root.iter():
        tag = element.tag
        if tag == "list":
            element.tag = element.get("rend", "ul").split("-", 1)[0]
            if "rend" in element.attrib:
                _ = element.attrib.pop("rend")
        elif tag == "item":
            element.tag = element.get("rend", "li").split("-", 1)[0]
            if "rend" in element.attrib:
                _ = element.attrib.pop("rend")
        elif tag == "head":
            element.tag = element.get("rend", "h2").split("-", 1)[0]
            if "rend" in element.attrib:
                _ = element.attrib.pop("rend")
        elif tag == "row":
            element.tag = "tr"
        elif tag == "cell":
            element.tag = "th" if element.get("role") == "head" else "td"
            if "role" in element.attrib:
                _ = element.attrib.pop("role")
        elif tag == "graphic":
            element.tag = "img"
        elif tag == "ref":
            element.tag = "a"
            target = element.get("target")
            if target is not None:
                del element.attrib["target"]
                element.set("href", target)
        elif tag == "lb":
            element.tag = "br"

    containers = [element for element in root if element.tag in {"main", "comments"}]
    content = [child for container in containers for child in container]
    return content or [root]


def _html_to_markdown(element: etree._Element, params: ScrapeParams) -> str:
    converter = html2text.HTML2Text()
    # `_strip_configured_tags` already drops these tags below each content root, but not a root that is one.
    converter.ignore_links = not params.scrape_links
    converter.ignore_images = not params.scrape_images
    serialized = cast(str, lxml_html.tostring(element, encoding="unicode", method="html"))
    return converter.handle(serialized)


def _main_content_markdown(snapshot: BrowserSnapshot, params: ScrapeParams) -> str:
    """The page's main content (its `<main>`, articles, or a conventional content id; trafilatura otherwise)
    as markdown, read with a single low-memory lxml DOM."""
    try:
        root = lxml_html.document_fromstring(snapshot.html_content)
    except (etree.ParserError, ValueError) as error:
        raise EmptyPageContentError(url=snapshot.metadata.url, nb_retries=1) from error

    for tag in _MAIN_CONTENT_REMOVED_TAGS:
        for element in list(root.iter(tag)):
            _remove_subtree(element)
    _remove_hidden_elements(root)

    main = next(root.iter("main"), None)
    if main is not None:
        articles = list(main.iter("article"))
        content = articles or [main]
    else:
        articles = list(root.iter("article"))
        content = articles or ([] if (deepest := _deepest_content_id(root)) is None else [deepest])

    if not content:
        content = _trafilatura_fallback(snapshot.html_content)
    if not content:
        raise EmptyPageContentError(url=snapshot.metadata.url, nb_retries=1)

    _strip_configured_tags(content, params.removed_tags())
    data = "\n\n".join(filter(None, (_html_to_markdown(element, params).strip() for element in content)))
    if not data:
        raise EmptyPageContentError(url=snapshot.metadata.url, nb_retries=1)
    return data


class VisibleMarkdownConverter(MarkdownConverter):
    """Ignore hidden content on the page."""

    @override
    def convert_soup(self, soup: BeautifulSoup) -> str | Any:
        for element in soup.find_all(style=True):
            if not hasattr(element, "attrs") or element.attrs is None:  # pyright: ignore [reportUnnecessaryComparison]
                continue

            # case-sensitive, unlike the main-content path: kept so that full-page output does not change
            if _hides(element.get("style", "")):  # pyright: ignore [reportArgumentType]
                element.decompose()

        return super().convert_soup(soup)


# Page-side implementation: js/frame_element_position.js
_FRAME_ELEMENT_POSITION = script("frame_element_position.js")


async def _frames_in_document_order(frame: Frame) -> list[Frame]:
    """`frame` and its descendants, each followed by its children in the order of their elements in its document.

    `page.frames` lists frames in the order they attached, which varies between runs (e.g. cross-origin frames).
    """
    positions: list[tuple[float, Frame]] = []
    for child in frame.child_frames:
        try:
            position = float(await (await child.frame_element()).evaluate(_FRAME_ELEMENT_POSITION))
        except PlaywrightError:
            position = float("inf")  # detached while we were looking: keep it last
        positions.append((position, child))
    frames = [frame]
    for _, child in sorted(positions, key=lambda item: item[0]):
        frames.extend(await _frames_in_document_order(child))
    return frames


async def page_markdown(window: BrowserWindow, snapshot: BrowserSnapshot, params: ScrapeParams) -> str:
    """The page as markdown: the whole page (markdownify), or only its main content (html2text) with
    `params.only_main_content`, followed by each iframe's content in document order unless `params.selector`
    scopes the scrape.

    Iframes are read from the live frames rather than the snapshot so that cross-origin frames remain readable.
    """
    converter = VisibleMarkdownConverter(strip=params.removed_tags())
    if params.only_main_content:
        content = _main_content_markdown(snapshot, params)
    else:
        content = converter.convert(snapshot.html_content)

    if params.selector is None:
        for iframe in await _frames_in_document_order(window.page.main_frame):
            if iframe.url != window.page.url and not iframe.url.startswith("data:"):
                try:
                    iframe_content = await iframe.content()
                    content += f"\n\nIFRAME {iframe.url}:\n"
                    content += converter.convert(iframe_content)
                except PlaywrightError as error:
                    logger.warning(f"Failed to get iframe content for {iframe.url}: {error}")

    return content
