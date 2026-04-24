import datetime as dt
import mimetypes
import re
from typing import Any
from urllib.parse import parse_qs, urlparse

from notte_core.browser.dom_tree import ComputedDomAttributes, DomAttributes, DomNode, NodeSelectors
from notte_core.browser.node_type import NodeRole, NodeType

DEFAULT_RAW_FILE_SELECTORS = tuple(["body", "html"])


def _normalize_ext(ext: str | None) -> str | None:
    if not ext:
        return None
    return ext.lstrip(".").lower() or None


def _ext_from_content_type(content_type: str) -> str | None:
    # Strip parameters like "; charset=utf-8" before looking up.
    primary = content_type.split(";", 1)[0].strip().lower()
    if not primary or primary.startswith("text/html") or primary.startswith("application/xhtml"):
        return None
    return _normalize_ext(mimetypes.guess_extension(primary))


def _ext_from_path(path: str) -> str | None:
    # mimetypes.guess_type covers hundreds of extensions via IANA + system
    # mime.types; drop the hardcoded allowlist in favor of it.
    guessed_type, _ = mimetypes.guess_type(path)
    if guessed_type is None:
        return None
    return _ext_from_content_type(guessed_type)


def match_extension(path: str) -> str | None:
    return _ext_from_path(path)


def get_file_ext(headers: dict[str, Any] | None, url: str | None) -> str | None:
    if headers is not None:
        if "content-type" not in headers:
            return None
        return _ext_from_content_type(headers["content-type"])

    if url is None:
        return None

    # Fallback used when the response object is gone: try the URL path first,
    # then values of query parameters (some download URLs stash the filename
    # in a query param, e.g. ?file=report.pdf).
    parsed_url = urlparse(url)
    candidates: list[str] = [parsed_url.path]
    for values in parse_qs(parsed_url.query).values():
        candidates.extend(v.strip() for v in values)

    for candidate in candidates:
        ext = _ext_from_path(candidate)
        if ext:
            return ext
    return None


def get_filename(headers: dict[str, Any], url: str) -> str:
    match: re.Match[str] | None = None

    if "content-disposition" in headers:
        match = re.search('filename="(.+)"', headers["content-disposition"])

    if match:
        filename = match.group(1)
        filename = filename.replace("/", "-")
    else:
        host = urlparse(url).hostname
        filename = (host or "") + (get_file_ext(headers, url) or "")
    now = dt.datetime.now(dt.timezone.utc)
    filename = f"{now.strftime('%Y_%m_%d_%H_%M_%S')}-{filename}"
    return filename


def get_empty_dom_node(id: str, text: str) -> DomNode:
    return DomNode(
        id=id,
        type=NodeType.INTERACTION,
        role=NodeRole.BUTTON,
        text=text,
        attributes=DomAttributes.safe_init(tag_name="button", value=text),
        children=[],
        computed_attributes=ComputedDomAttributes(
            is_interactive=True,
            is_top_element=True,
            selectors=NodeSelectors.from_unique_selector(DEFAULT_RAW_FILE_SELECTORS[0]),
        ),
    )
