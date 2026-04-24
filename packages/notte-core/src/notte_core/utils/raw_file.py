import datetime as dt
import mimetypes
import re
from typing import Any
from urllib.parse import parse_qs, urlparse

from notte_core.browser.dom_tree import ComputedDomAttributes, DomAttributes, DomNode, NodeSelectors
from notte_core.browser.node_type import NodeRole, NodeType

DEFAULT_RAW_FILE_SELECTORS = tuple(["body", "html"])

# Web-page / server-rendered extensions — these URLs serve HTML, not files.
_EXCLUDED_PATH_EXTS = frozenset({"html", "htm", "xhtml", "aspx", "asp", "php", "jsp", "cfm"})


def match_extension(path: str) -> str | None:
    # Extract extension from a filesystem-like path deterministically (no
    # OS-dependent mimetypes round-trip: `guess_extension("text/plain")`
    # returns ".ksh" on Linux vs ".txt" on macOS).
    if "." not in path:
        return None
    ext = path.rsplit(".", 1)[-1].lower()
    if not ext or "/" in ext or len(ext) > 10 or ext in _EXCLUDED_PATH_EXTS:
        return None
    return ext


def _ext_from_content_type(content_type: str) -> str | None:
    # Strip parameters like "; charset=utf-8" before looking up.
    primary = content_type.split(";", 1)[0].strip().lower()
    if not primary or primary.startswith("text/html") or primary.startswith("application/xhtml"):
        return None
    return mimetypes.guess_extension(primary)


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
        ext = match_extension(candidate)
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
