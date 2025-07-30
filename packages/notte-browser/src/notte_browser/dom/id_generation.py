import re
from collections import defaultdict
from dataclasses import dataclass
from urllib.parse import urlparse

from loguru import logger
from notte_core.browser.node_type import NodeRole
from notte_core.profiling import profiler

from notte_browser.dom.types import DOMBaseNode, DOMElementNode


@dataclass
class URLCacheEntry:
    """Cache entry for a base URL containing ID counter and XPath mappings."""

    id_counter: defaultdict[str, int]
    xpath_to_id: dict[str, tuple[NodeRole, str]]

    def normalize_xpath(self, xpath: str) -> str:
        # Remove the [1] index from the xpath
        # This is required beacuse sometimes the xpath generation is not deterministic and adds a [1] index even though the element is the same
        # E.g. address field in the checkout page: https://shop.notte.cc/checkout/ch_xsbVu-D7SwKE25vyY0zd3w
        # => when we input the address, the xpath becomes:
        # html/body/div[1]/div[2]/div/div/div[1]/main/form/div[2]/div[2]/fieldset/div[3]/div/div/div[1]/div/div/div/input
        # html/body/div[1]/div[2]/div/div/div[1]/main/form/div[2]/div[2]/fieldset/div[3]/div/div/div[1]/div[1]/div/div/input
        return re.sub(r"\[1\]", "", xpath)

    def get_id(self, xpath: str, role: NodeRole) -> str:
        xpath = self.normalize_xpath(xpath)
        if xpath in self.xpath_to_id:
            hit_role, hit_id = self.xpath_to_id[xpath]
            if hit_role == role:
                return hit_id
            logger.error(
                f"XPath {xpath} has been used for both {hit_role} and {role}. This is not allowed. Creating a new ID for {role}."
            )
        id = role.short_id(force_id=True)
        if id is None:
            raise ValueError(
                (
                    f"Role {role} was incorrectly converted from raw Dom Node."
                    " It is an interaction node. It should have a short ID but is currently None"
                )
            )
        notte_id = f"{id}{self.id_counter[id]}"
        self.id_counter[id] += 1
        self.xpath_to_id[xpath] = (role, notte_id)
        return notte_id


# Global cache for URL-based ID counters
_url_id_cache: dict[str, URLCacheEntry] = {}


def get_cache_entry(url: str) -> URLCacheEntry:
    parsed_url = urlparse(url)
    cache_key = f"{parsed_url.netloc}{parsed_url.path}"
    if cache_key not in _url_id_cache:
        _url_id_cache[cache_key] = URLCacheEntry(id_counter=defaultdict(lambda: 1), xpath_to_id={})
    return _url_id_cache[cache_key]


@profiler.profiled()
def generate_sequential_ids(root: DOMBaseNode, url: str) -> DOMBaseNode:
    """
    Generates sequential IDs for interactive elements in the accessibility tree
    using depth-first search with URL-based XPath caching.
    """
    stack = [root]
    cache_entry = get_cache_entry(url)
    while stack:
        node = stack.pop()
        children = node.children

        role = NodeRole.from_value(node.role) if isinstance(node.role, str) else node.role  # type: ignore
        if isinstance(role, str):
            logger.debug(
                f"Unsupported role to convert to ID: {node}. Please add this role to the NodeRole e logic ASAP."
            )
        elif node.highlight_index is not None:
            assert isinstance(node, DOMElementNode), f"Node {node} is not a DOMElementNode"
            node.notte_id = cache_entry.get_id(node.xpath, role)
        stack.extend(reversed(children))

    return root
