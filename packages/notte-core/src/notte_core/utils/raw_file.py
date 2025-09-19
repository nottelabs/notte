import datetime as dt
import mimetypes
import re
from typing import Any
from urllib.parse import urlparse

from notte_core.browser.dom_tree import ComputedDomAttributes, DomAttributes, DomNode, NodeSelectors
from notte_core.browser.node_type import NodeRole, NodeType


def get_file_ext(headers: dict[str, Any] | None, url: str | None) -> str | None:
    if headers is None:
        if url is None:
            return None
        # Parse URL to get the path component, ignoring queries and fragments
        parsed_url = urlparse(url)
        path = parsed_url.path
        # Extract extension from the path
        if "." in path:
            extension = path.split(".")[-1].lower()
            if extension in [
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
            ]:
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
            selectors=NodeSelectors.from_unique_selector("html"),
        ),
    )
