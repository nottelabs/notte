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
from notte_core.types import ScrapeParams
from typing_extensions import override

from notte_browser.errors import EmptyPageContentError, PlaywrightError
from notte_browser.playwright_async_api import Frame
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

            style = element.get("style", "")
            if "display:none" in style.replace(" ", "") or "visibility:hidden" in style.replace(" ", ""):  # pyright: ignore [reportOptionalMemberAccess, reportAttributeAccessIssue]
                element.decompose()

        return super().convert_soup(soup)  # pyright: ignore [reportUnknownVariableType]


# position of an iframe element among its document's elements (iframes in a shadow root take their host's position)
_FRAME_ELEMENT_POSITION = """el => {
    let node = el;
    while (node.getRootNode() instanceof ShadowRoot) node = node.getRootNode().host;
    return Array.prototype.indexOf.call(node.ownerDocument.getElementsByTagName("*"), node);
}"""


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
        content = cast(str, converter.convert(snapshot.html_content))

    if params.selector is None:
        for iframe in await _frames_in_document_order(window.page.main_frame):
            if iframe.url != window.page.url and not iframe.url.startswith("data:"):
                try:
                    iframe_content = await iframe.content()
                    content += f"\n\nIFRAME {iframe.url}:\n"
                    content += cast(str, converter.convert(iframe_content))
                except PlaywrightError as error:
                    logger.warning(f"Failed to get iframe content for {iframe.url}: {error}")

    return content
