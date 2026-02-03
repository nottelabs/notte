import datetime as dt
import mimetypes
import re
from typing import Any
from urllib.parse import parse_qs, urlparse

from notte_core.browser.dom_tree import ComputedDomAttributes, DomAttributes, DomNode, NodeSelectors
from notte_core.browser.node_type import NodeRole, NodeType

DEFAULT_RAW_FILE_SELECTORS = ["body", "html"]


def match_extension(path: str) -> str | None:
    if "." in path:
        extension = path.split(".")[-1].lower()
        if extension.lower() in [
            "pdf",
            "doc",
            "docx",
            "xls",
            "xlsx",
            "ppt",
            "pptx",
            "png",
            "jpg",
            "jpeg",
            "gif",
            "bmp",
            "tiff",
            "ico",
            "webp",
            "mp4",
            "mp3",
            "wav",
            "ogg",
            "avi",
            "mov",
            "wmv",
            "flv",
            "webm",
            "mkv",
            "mpeg",
            "mpg",
        ]:
            return extension
    return None


def get_file_ext(headers: dict[str, Any] | None, url: str | None) -> str | None:
    if headers is None:
        if url is None:
            return None
        # Parse URL to get the path component, ignoring queries and fragments
        parsed_url = urlparse(url)
        params = parse_qs(parsed_url.query)
        param_values: list[str] = [value.strip() for _, values in params.items() for value in values]
        path = parsed_url.path

        trials = [
            path,
            *param_values,
        ]

        # Extract extension from the path
        for trial in trials:
            extension = match_extension(trial)
            if extension:
                return extension
        return None

    if "content-type" not in headers:
        return None
    return mimetypes.guess_extension(headers["content-type"])


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
    now = dt.datetime.now()
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
