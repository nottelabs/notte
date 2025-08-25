import mimetypes
import re
import time
from typing import Any
from urllib.parse import urlparse

from notte_core.browser.dom_tree import ComputedDomAttributes, DomAttributes, DomNode, NodeSelectors
from notte_core.browser.node_type import NodeRole, NodeType


def get_file_ext(headers: dict[str, Any]) -> str:
    if "content-type" not in headers:
        return ""

    return mimetypes.guess_extension(headers["content-type"]) or ""


def get_filename(headers: dict[str, Any], url: str) -> str:
    match: re.Match[str] | None = None

    if "content-disposition" in headers:
        match = re.search('filename="(.+)"', headers["content-disposition"])

    if match:
        filename = match.group(1)
        filename = filename.replace("/", "-")
    else:
        host = urlparse(url).hostname
        filename = (host or "") + get_file_ext(headers)

    filename = f"{str(round(time.time()))}-{filename}"
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
