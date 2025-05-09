import fnmatch
from typing import Callable, Self, TypeAlias
from urllib.parse import urlparse

from pydantic import BaseModel

from notte_core.browser.dom_tree import DomNode
from notte_core.browser.node_type import NodeRole

NodePredicate: TypeAlias = Callable[[DomNode], bool]


class ActionAllowList(BaseModel):
    predicates: list[NodePredicate] = []

    def add_predicate(self, predicate: NodePredicate) -> None:
        self.predicates.append(predicate)

    def hide_by_text(self, text: str) -> Self:
        def predicate(node: DomNode) -> bool:
            return node.text == text

        self.add_predicate(predicate)
        return self

    def hide_by_role(self, role: NodeRole) -> Self:
        def predicate(node: DomNode) -> bool:
            return node.role == role

        self.add_predicate(predicate)
        return self

    def hide_by_class(self, claz: str) -> Self:
        def predicate(node: DomNode) -> bool:
            if node.attributes is None:
                return False

            return node.attributes.class_name == claz

        self.add_predicate(predicate)
        return self

    def hide_by_id(self, id_: str) -> Self:
        def predicate(node: DomNode) -> bool:
            if node.attributes is None:
                return False
            return node.attributes.elem_id == id_

        self.add_predicate(predicate)
        return self

    def hide_by_tag(self, tag: str) -> Self:
        def predicate(node: DomNode) -> bool:
            if node.attributes is None:
                return False

            return node.attributes.tag_name == tag

        self.add_predicate(predicate)
        return self

    def should_hide(self, node: DomNode) -> bool:
        return any(predicate(node) for predicate in self.predicates)

    def should_keep(self, node: DomNode) -> bool:
        return not self.should_hide(node)

    def filter_tree(self, node: DomNode) -> DomNode:
        fnode = node.subtree_filter(lambda n: self.should_keep(n))
        if fnode is None:
            raise ValueError("Filters removed all nodes from page: try relaxing them")

        return fnode


class URLAllowList:
    def __init__(self):
        self.whitelist: list[str] = []
        self.blacklist: list[str] = []

    def add_to_whitelist(self, pattern: str) -> None:
        """
        Add a glob pattern to the whitelist.

        Args:
            pattern: A glob pattern to match URLs (e.g., "*.example.com/*", "sub.example.com/*/search/?*")
        """
        # Convert to lowercase for case-insensitive matching
        _ = self.whitelist.append(pattern.lower())

    def add_to_blacklist(self, pattern: str) -> None:
        """
        Add a glob pattern to the blacklist.

        Args:
            pattern: A glob pattern to match URLs (e.g., "*.example.com/*", "sub.example.com/*/search/?*")
        """
        # Convert to lowercase for case-insensitive matching
        self.blacklist.append(pattern.lower())

    def remove_from_whitelist(self, pattern: str) -> None:
        """Remove a pattern from the whitelist."""
        pattern_lower = pattern.lower()
        if pattern_lower in self.whitelist:
            self.whitelist.remove(pattern_lower)

    def remove_from_blacklist(self, pattern: str) -> None:
        """Remove a pattern from the blacklist."""
        pattern_lower = pattern.lower()
        if pattern_lower in self.blacklist:
            self.blacklist.remove(pattern_lower)

    def is_allowed(self, url: str) -> bool:
        """
        Check if a URL is allowed based on whitelist and blacklist.

        If whitelist is empty, all URLs except those in blacklist are allowed.
        If whitelist is not empty, only URLs in whitelist and not in blacklist are allowed.

        Returns:
            bool: True if URL is allowed, False otherwise
        """
        # Normalize the URL for matching
        normalized_url = self._normalize_url(url)

        # Check if URL matches any blacklist pattern
        # unless also in whitelist
        matches_blacklist = any(self._match_pattern(normalized_url, pattern) for pattern in self.blacklist)
        matches_whitelist = any(self._match_pattern(normalized_url, pattern) for pattern in self.blacklist)

        # if match both or just whitelist, accept
        if matches_whitelist:
            return True

        # if match only blacklist, reject
        elif matches_blacklist:
            return False

        # If whitelist is empty, allow all non-blacklisted URLs
        if not self.whitelist:
            return True

        # URL is not in whitelist
        return False

    def _normalize_url(self, url: str) -> str:
        """
        Normalize a URL for matching against patterns.

        Handles URLs with or without scheme, removes trailing slashes, converts to lowercase.
        """
        # If URL doesn't have a scheme, add one to help urlparse
        if not url.startswith(("http://", "https://")):
            url = "http://" + url

        parsed = urlparse(url)

        # Combine domain and path, removing trailing slash
        normalized = parsed.netloc + parsed.path
        if normalized.endswith("/"):
            normalized = normalized[:-1]

        # Add query parameters if they exist
        if parsed.query:
            normalized += "?" + parsed.query

        return normalized.lower()

    def _match_pattern(self, url: str, pattern: str) -> bool:
        """
        Match a URL against a glob pattern.

        Uses fnmatch for glob-style matching with * and ? wildcards.
        """
        return fnmatch.fnmatch(url, pattern)
