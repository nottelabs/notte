# pyright: reportPrivateUsage=false, reportUnknownMemberType=false

from typing import Any, cast

import html2text
import trafilatura
from bs4 import BeautifulSoup
from lxml import etree
from lxml import html as lxml_html
from markdownify import MarkdownConverter  # pyright: ignore [reportMissingTypeStubs]
from notte_core.browser.snapshot import BrowserSnapshot
from notte_core.common.logging import logger
from notte_sdk.types import ScrapeParams
from typing_extensions import override

from notte_browser.errors import EmptyPageContentError, PlaywrightError
from notte_browser.window import BrowserWindow

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


def _remove_hidden_elements(root: etree._Element) -> None:
    for element in list(root.iter()):
        style = str(element.get("style", "")).replace(" ", "").lower()
        if "display:none" in style or "visibility:hidden" in style:
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


def _html_to_markdown(element: etree._Element, params: ScrapeParams, *, images_to_alt: bool) -> str:
    converter = html2text.HTML2Text()
    converter.ignore_links = not params.scrape_links
    converter.ignore_images = not params.scrape_images
    converter.images_to_alt = images_to_alt
    serialized = cast(str, lxml_html.tostring(element, encoding="unicode", method="html"))
    return converter.handle(serialized)


class MainContentScrapingPipe:
    """Extract main content with a single low-memory lxml DOM."""

    @staticmethod
    def forward(snapshot: BrowserSnapshot, params: ScrapeParams, *, images_to_alt: bool = False) -> str:
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
        data = "\n\n".join(
            filter(
                None, (_html_to_markdown(element, params, images_to_alt=images_to_alt).strip() for element in content)
            )
        )
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

            style = element.get("style", "")
            if "display:none" in style.replace(" ", "") or "visibility:hidden" in style.replace(" ", ""):  # pyright: ignore [reportOptionalMemberAccess, reportAttributeAccessIssue]
                element.decompose()

        return super().convert_soup(soup)  # pyright: ignore [reportUnknownVariableType]


class MarkdownifyScrapingPipe:
    """Convert page content to Markdown and append readable iframe content."""

    @staticmethod
    async def forward(
        window: BrowserWindow,
        snapshot: BrowserSnapshot,
        params: ScrapeParams,
        include_iframes: bool | None = None,
    ) -> str:
        converter = VisibleMarkdownConverter(strip=params.removed_tags())
        if params.only_main_content:
            content = MainContentScrapingPipe.forward(snapshot, params)
        else:
            content = converter.convert(snapshot.html_content)  # type: ignore[attr-defined]

        # Manually append iframe text so cross-origin frames remain readable.
        # Do not include iframes by default when a selector scopes the scrape.
        if include_iframes is None:
            include_iframes = params.selector is None

        if include_iframes:
            for iframe in window.page.frames:
                if iframe.url != window.page.url and not iframe.url.startswith("data:"):
                    try:
                        iframe_content = await iframe.content()
                        content += f"\n\nIFRAME {iframe.url}:\n"  # type: ignore[attr-defined]
                        content += converter.convert(iframe_content)  # type: ignore[attr-defined]
                    except PlaywrightError as error:
                        logger.warning(f"Failed to get iframe content for {iframe.url}: {error}")

        return content  # type: ignore[return-value]
