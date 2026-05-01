import datetime as dt
import mimetypes
import re
from typing import Any
from urllib.parse import parse_qs, urlparse

from notte_core.browser.dom_tree import ComputedDomAttributes, DomAttributes, DomNode, NodeSelectors
from notte_core.browser.node_type import NodeRole, NodeType

DEFAULT_RAW_FILE_SELECTORS = tuple(["body", "html"])

# Best-effort allowlist of extensions we treat as "downloadable raw files".
# This drives a synthetic "download this page" hint surfaced to the agent when
# it lands on a non-HTML URL (see `window.snapshot`). A miss just means the
# agent fumbles the DOM for a step or two; a false positive writes junk bytes
# the agent discards. It is not safety-critical, so keep this list short and
# don't try to be exhaustive.
_KNOWN_FILE_EXTS: frozenset[str] = frozenset(
    {
        # documents
        "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx",
        # text / structured data
        "txt", "md", "csv", "json", "xml", "yaml", "yml",
        # images
        "png", "jpg", "jpeg", "gif", "bmp", "tiff", "webp", "svg", "ico",
        # archives
        "zip", "tar", "gz", "bz2", "7z", "rar",
        # audio / video
        "mp3", "wav", "ogg", "mp4", "webm", "mov", "avi", "mkv", "flv", "wmv", "mpeg", "mpg",
    }
)  # fmt: skip


def match_extension(path: str) -> str | None:
    if "." not in path:
        return None
    ext = path.rsplit(".", 1)[-1].lower()
    return ext if ext in _KNOWN_FILE_EXTS else None


def _ext_from_content_type(content_type: str) -> str | None:
    # Strip parameters like "; charset=utf-8" before looking up.
    primary = content_type.split(";", 1)[0].strip().lower()
    if not primary:
        return None
    guessed = mimetypes.guess_extension(primary)
    if not guessed:
        return None
    ext = guessed.lstrip(".").lower()
    return ext if ext in _KNOWN_FILE_EXTS else None


def get_file_ext(headers: dict[str, Any] | None, url: str | None) -> str | None:
    if headers is not None:
        if "content-type" not in headers:
            return None
        return _ext_from_content_type(headers["content-type"])

    if url is None:
        return None

    # URL-only fallback when the response object is gone. The allowlist makes
    # this safe to run against every query value — opaque tokens won't collide
    # with known file extensions.
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
        ext = get_file_ext(headers, url)
        filename = (host or "") + (f".{ext}" if ext else "")
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
