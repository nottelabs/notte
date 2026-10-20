"""A failing or slow selector generator falls back to CSS / XPath and says so at warning level."""

import asyncio
from collections.abc import Iterator
from dataclasses import replace
from unittest.mock import MagicMock

import notte_browser.resolution as resolution_module
import notte_core.logging as logging
import pytest
from notte_browser.driver import ElementHandle
from notte_browser.resolution import generate_playwright_selector, set_selector_generator
from notte_core.dom_tree import DomNode, NodeSelectors

from tests.mock.snapshot_factory import make_snapshot

SECRET = "#account-42 >> text=hunter2"

SELECTORS = NodeSelectors(
    css_selector="#go",
    xpath_selector="//button",
    in_iframe=False,
    in_shadow_root=False,
    iframe_parent_css_selectors=[],
)


@pytest.fixture
def node() -> DomNode:
    dom_node = make_snapshot("https://example.com").dom_node
    return replace(
        dom_node,
        id="B1",
        computed_attributes=replace(dom_node.computed_attributes, handle=MagicMock(), selectors=SELECTORS),
    )


@pytest.fixture
def backend_logger(monkeypatch: pytest.MonkeyPatch) -> Iterator[MagicMock]:
    backend_logger = MagicMock()
    monkeypatch.setattr(logging, "get_logger", lambda: backend_logger)
    yield backend_logger
    set_selector_generator(None)


def _warning(backend_logger: MagicMock) -> str:
    backend_logger.warning.assert_called_once()
    message = backend_logger.warning.call_args.args[0]
    assert isinstance(message, str)
    assert "B1" in message
    # neither selectors nor exception messages are logged
    assert SECRET not in message and "#go" not in message
    return message


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [RuntimeError(SECRET), TimeoutError(SECRET)], ids=["runtime", "own-timeout"])
async def test_generator_error_is_logged_with_its_type(
    node: DomNode, backend_logger: MagicMock, error: Exception
) -> None:
    async def generator(_handle: ElementHandle, _selectors: NodeSelectors) -> str | None:
        raise error

    set_selector_generator(generator)
    assert await generate_playwright_selector(node, SELECTORS) is None

    message = _warning(backend_logger)
    assert f"({type(error).__name__})" in message
    assert "timed out" not in message


@pytest.mark.asyncio
async def test_generator_timeout_is_logged_as_a_timeout(
    node: DomNode, backend_logger: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(resolution_module, "SELECTOR_GENERATOR_TIMEOUT_S", 0.01)

    async def generator(_handle: ElementHandle, _selectors: NodeSelectors) -> str | None:
        await asyncio.sleep(10)
        return SECRET

    set_selector_generator(generator)
    assert await generate_playwright_selector(node, SELECTORS) is None

    message = _warning(backend_logger)
    assert "timed out after 0.01s" in message
    assert "failed" not in message


@pytest.mark.asyncio
async def test_generated_selector_logs_nothing(node: DomNode, backend_logger: MagicMock) -> None:
    async def generator(_handle: ElementHandle, _selectors: NodeSelectors) -> str | None:
        return "#generated"

    set_selector_generator(generator)
    assert await generate_playwright_selector(node, SELECTORS) == "#generated"
    backend_logger.warning.assert_not_called()
