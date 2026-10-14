"""Backend-owned windows and late-installed hooks remain usable through the session facade."""

from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock

import notte_browser.captcha as captcha_module
import notte_browser.resolution as resolution_module
import notte_core.common.logging as logging
import pytest
from notte_browser.captcha import captcha_solver_available, set_captcha_solver, solve_captcha
from notte_browser.errors import CaptchaSolverNotAvailableError
from notte_browser.playwright_async_api import Locator, Page
from notte_browser.resolution import set_selector_generator
from notte_browser.session import NotteSession
from notte_browser.window import BrowserWindow, BrowserWindowOptions, ScreenshotMask
from notte_core.actions import CaptchaSolveAction, ClickAction
from notte_core.browser.dom_tree import NodeSelectors
from notte_core.browser.node_type import NodeType
from notte_core.data.space import DataSpace, DictBaseModel
from notte_core.types import LocalSessionStartRequest
from typing_extensions import override

from tests.mock.mock_vault import MockVault
from tests.mock.snapshot_factory import make_snapshot


def _page() -> MagicMock:
    page = MagicMock(spec=Page)
    page.url = "https://example.com"
    page.is_closed.return_value = False
    page.context.pages = [page]
    return page


@pytest.mark.asyncio
async def test_borrowed_window_callbacks_page_assignment_and_custom_mask() -> None:
    page, replacement = _page(), _page()
    events: list[str] = []
    callback = MagicMock()
    mask_call = AsyncMock(return_value=[MagicMock(spec=Locator)])

    class CustomMask(ScreenshotMask):
        @override
        async def mask(self, page: Page) -> list[Locator]:
            return await mask_call(page)

    async def close_borrowed() -> None:
        events.append("external.close")

    mask = CustomMask()
    window = BrowserWindow(
        page=page,
        options=BrowserWindowOptions.from_request(LocalSessionStartRequest()),
        screenshot_mask=mask,
        on_close=close_borrowed,
    )
    window.page_callbacks["load"] = callback
    window.apply_page_callbacks()
    session = NotteSession(window=window, vault=MockVault({}))
    assert session.window is window
    page.on.assert_any_call("load", callback)
    window.page = replacement
    assert window.page is replacement
    replacement.on.assert_any_call("load", callback)
    session.vault = None
    assert window.screenshot_mask is mask
    replacement.screenshot.return_value = b"jpeg"
    assert await window.screenshot() == b"jpeg"
    mask_call.assert_awaited_once_with(replacement)
    replacement.screenshot.assert_awaited_once_with(mask=mask_call.return_value, type="jpeg", quality=85)
    replacement.close.side_effect = lambda: events.append("page.close")
    await window.close()
    assert events == ["external.close"]
    replacement.close.assert_not_awaited()


@pytest.mark.asyncio
async def test_hooks_registered_after_session_construction_are_used(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(captcha_module, "_solver", None)
    monkeypatch.setattr(resolution_module, "_selector_generator", None)
    page = _page()
    window = BrowserWindow(page=page, options=BrowserWindowOptions.from_request(LocalSessionStartRequest()))
    session = NotteSession(window=window)
    snapshot = make_snapshot(page.url)
    snapshot.dom_node = replace(snapshot.dom_node, id="B1", type=NodeType.INTERACTION, text="Submit")
    session.snapshot = snapshot
    selectors = NodeSelectors(
        css_selector="#backend",
        xpath_selector="//button",
        in_iframe=False,
        in_shadow_root=False,
        iframe_parent_css_selectors=[],
    )
    handle = MagicMock()
    snapshot.dom_node = replace(
        snapshot.dom_node,
        computed_attributes=replace(snapshot.dom_node.computed_attributes, handle=handle, selectors=selectors),
    )
    resolver = AsyncMock(return_value="#backend")
    set_selector_generator(resolver)
    locator = MagicMock(spec=Locator)
    page.locator.return_value = locator
    locator.count = AsyncMock(return_value=1)
    locator.evaluate.return_value = False
    assert await session.locate(ClickAction(id="B1")) is locator
    result = await session.aexecute(ClickAction(id="B1"), raise_on_failure=True)
    assert result.success
    assert resolver.await_count == 2
    locator.click.assert_awaited_once()

    assert not captcha_solver_available()
    with pytest.raises(CaptchaSolverNotAvailableError):
        NotteSession(window=window, solve_captchas=True)
    handler = AsyncMock(return_value=True)
    set_captcha_solver(handler)
    assert captcha_solver_available()
    assert NotteSession(window=window, solve_captchas=True).window is window
    action = CaptchaSolveAction()
    assert (await session.aexecute(action, raise_on_failure=True)).success
    handler.assert_awaited_once_with(window, action)
    replacement = AsyncMock(return_value=True)
    set_captcha_solver(replacement)
    assert (await session.aexecute(action, raise_on_failure=True)).success
    replacement.assert_awaited_once_with(window, action)
    set_captcha_solver(None)
    assert not captcha_solver_available()
    with pytest.raises(CaptchaSolverNotAvailableError):
        await solve_captcha(window, action)
    set_selector_generator(None)


def test_imported_logger_uses_replaced_provider_and_structured_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    from notte_browser.resolution import logger

    backend_logger = MagicMock()
    monkeypatch.setattr(logging, "get_logger", lambda: backend_logger)
    logger.info("backend message")
    backend_logger.info.assert_called_once_with("backend message")
    data = DictBaseModel([{"message": "mail"}])
    space = DataSpace.from_structured(data)
    assert space.markdown == "No markdown available"
    assert space.structured is not None
    assert space.structured.get() == [{"message": "mail"}]
    assert space.model_dump()["structured"] == {"success": True, "error": None, "data": [{"message": "mail"}]}
