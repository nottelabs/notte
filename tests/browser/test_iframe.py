from pathlib import Path
from typing import Any, TypeAlias
from unittest import TestCase

import pytest
from notte_browser.dom.parsing import DomParsingConfig, DomTreeDict, ParseDomTreePipe
from notte_browser.dom.types import DOMBaseNode
from notte_browser.session import NotteSession, NotteSessionConfig
from notte_core.errors.processing import SnapshotProcessingError
from patchright.async_api import Page

from tests.mock.mock_service import MockLLMService

DomList: TypeAlias = list[Any]


def node_to_sorted_list(node: DOMBaseNode, max_depth: int) -> DomList:
    def _node_to_dict(node: DOMBaseNode, max_depth: int) -> dict[Any, Any]:
        if max_depth <= 0:
            return {}

        curr = {"name": node.name, "role": node.role}
        curr["children"] = [_node_to_dict(child, max_depth - 1) for child in node.children]  # pyright: ignore[reportArgumentType]

        return curr

    def ordered(obj) -> list[Any]:
        if isinstance(obj, dict):
            return sorted((k, ordered(v)) for k, v in obj.items())
        if isinstance(obj, list):
            return sorted(ordered(x) for x in obj)
        else:
            return obj

    unsorted = _node_to_dict(node, max_depth)
    return ordered(unsorted)


async def old_parse_dom_tree(page: Page, config: DomParsingConfig) -> DOMBaseNode:
    js_code = Path("tests/browser/oldBuildDom.js").read_text()

    node: DomTreeDict | None = await page.evaluate(js_code, config.model_dump())
    if node is None:
        raise SnapshotProcessingError(page.url, "Failed to parse HTML to dictionary")
    parsed = ParseDomTreePipe._parse_node(
        node,
        parent=None,
        in_iframe=False,
        in_shadow_root=False,
        iframe_parent_css_paths=[],
        notte_selector=page.url,
    )
    if parsed is None:
        raise SnapshotProcessingError(page.url, f"Failed to parse DOM tree. Dom Tree is empty. {node}")
    return parsed


async def get_parsed_nodes_single_session(website_url: str, max_depth: int) -> tuple[DomList, DomList]:
    """Parse nodes from the same session (both with disabled security)

    Prefer testing with multi_session method, but this can help to debug
    """
    config = DomParsingConfig()

    # start browser with disabled web security, old parse dom tree
    old_session = NotteSession(
        config=NotteSessionConfig().disable_perception().headless().disable_web_security(),
        llmserve=MockLLMService(mock_response=""),
    )

    async with old_session as sesh:
        _ = await sesh.goto(website_url)
        await sesh.window.long_wait()
        old_res = node_to_sorted_list(await old_parse_dom_tree(sesh.window.page, config), max_depth=max_depth)
        new_res = node_to_sorted_list(
            await ParseDomTreePipe.parse_dom_tree(sesh.window.page, config), max_depth=max_depth
        )

    return old_res, new_res


async def get_parsed_nodes_multi_session(website_url: str, max_depth: int) -> tuple[DomList, DomList]:
    """Parse nodes from the same session (old with disabled security, new without)"""
    config = DomParsingConfig()

    old_session = NotteSession(
        config=NotteSessionConfig().disable_perception().headless().disable_web_security(),
        llmserve=MockLLMService(mock_response=""),
    )
    new_session = NotteSession(
        config=NotteSessionConfig().disable_perception().headless().enable_web_security(),
        llmserve=MockLLMService(mock_response=""),
    )

    # start browser with disabled web security, old parse dom tree
    async with old_session as sesh:
        _ = await sesh.goto(website_url)
        await sesh.window.long_wait()
        old_res = node_to_sorted_list(await old_parse_dom_tree(sesh.window.page, config), max_depth=max_depth)

    # start browser with enabled web security, new parse dom tree
    async with new_session as sesh:
        _ = await sesh.goto(website_url)
        await sesh.window.long_wait()
        new_res = node_to_sorted_list(
            await ParseDomTreePipe.parse_dom_tree(sesh.window.page, config), max_depth=max_depth
        )

    return old_res, new_res


MULTI_WEBSITES = [
    "https://www.thetimes.com/",
    "https://www.espn.co.uk/",
]

SINGLE_WEBSITES = MULTI_WEBSITES + [
    "https://www.bbc.com/news",
]


@pytest.mark.asyncio
@pytest.mark.parametrize("url", SINGLE_WEBSITES)
async def test_parsing_disabled_websecurity_session(url: str):
    old_res, new_res = await get_parsed_nodes_single_session(url, max_depth=10)
    TestCase().assertListEqual(old_res, new_res)


@pytest.mark.asyncio
@pytest.mark.parametrize("url", MULTI_WEBSITES)
async def test_parsing_enabled_websecurity_session(url: str):
    old_res, new_res = await get_parsed_nodes_multi_session(url, max_depth=5)
    TestCase().assertListEqual(old_res, new_res)
