"""Backend-owned windows and late-installed hooks remain usable through the session facade."""

from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock

import notte_core.common.logging as logging
import pytest
from notte_browser.captcha import CaptchaHandler
from notte_browser.errors import CaptchaSolverNotAvailableError
from notte_browser.playwright import PlaywrightManager
from notte_browser.playwright_async_api import Browser, Locator, Page, Playwright
from notte_browser.resolution import NodeResolutionPipe
from notte_browser.session import NotteSession
from notte_browser.window import BrowserResource, BrowserWindow, BrowserWindowOptions, ScreenshotMask
from notte_core.actions import CaptchaSolveAction, ClickAction
from notte_core.browser.dom_tree import NodeSelectors
from notte_core.browser.node_type import NodeType
from notte_core.data.space import DataSpace, DictBaseModel
from notte_core.types import LocalSessionStartRequest
from pydantic import Field
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
async def test_pydantic_manager_subclass_dispatches_launch_resource_and_stop() -> None:
    events: list[str] = []
    page, browser, driver = _page(), MagicMock(spec=Browser), MagicMock(spec=Playwright)
    browser.close.side_effect = lambda: events.append("browser.close")
    driver.stop.side_effect = lambda: events.append("driver.stop")
    page.close.side_effect = lambda: events.append("page.close")

    class CDPSessionManager(PlaywrightManager):
        session_id: str = Field()
        client: Browser = Field(exclude=True)
        browser_type: str = Field(default="chromium")

        @override
        async def create_playwright_browser(self, options: BrowserWindowOptions) -> Browser:
            assert options.cdp_url == "http://localhost:9222"
            events.append("launch")
            return self.client

        @override
        async def get_browser_resource(self, options: BrowserWindowOptions, browser: Browser) -> BrowserResource:
            assert browser is self.client
            events.append("resource")
            return BrowserResource(page=page, options=options, browser_id=self.session_id, context_id="context")

        @override
        async def astop(self) -> None:
            events.append("manager.stop")
            await super().astop()

    manager = CDPSessionManager(session_id="session", client=browser)
    manager._playwright = driver
    window = await manager.new_window(
        BrowserWindowOptions.from_request(LocalSessionStartRequest()).set_cdp_url("http://localhost:9222")
    )
    assert manager.model_dump() == {"verbose": False, "session_id": "session", "browser_type": "chromium"}
    assert window.resource.browser_id == "session"
    assert window.resource.context_id == "context"
    assert "page" not in window.resource.model_dump()
    await window.close()
    assert events == ["launch", "resource", "browser.close", "manager.stop", "driver.stop", "page.close"]
    assert not manager.is_started()


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
        resource=BrowserResource(page=page, options=BrowserWindowOptions.from_request(LocalSessionStartRequest())),
        screenshot_mask=mask,
        on_close=close_borrowed,
        page_callbacks={"load": callback},
    )
    session = NotteSession(window=window, vault=MockVault({}))
    assert session.window is window
    page.on.assert_any_call("load", callback)
    window.page = replacement
    assert window.resource.page is replacement
    replacement.on.assert_any_call("load", callback)
    session.vault = None
    assert window.screenshot_mask is mask
    replacement.screenshot.return_value = b"jpeg"
    assert await window.screenshot() == b"jpeg"
    mask_call.assert_awaited_once_with(replacement)
    replacement.screenshot.assert_awaited_once_with(mask=mask_call.return_value, type="jpeg", quality=85)
    replacement.close.side_effect = lambda: events.append("page.close")
    await window.close()
    assert events == ["external.close", "page.close"]


@pytest.mark.asyncio
async def test_hooks_replaced_after_session_construction_are_used(monkeypatch: pytest.MonkeyPatch) -> None:
    page = _page()
    window = BrowserWindow(
        resource=BrowserResource(page=page, options=BrowserWindowOptions.from_request(LocalSessionStartRequest()))
    )
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
    resolver = AsyncMock(return_value=selectors)
    monkeypatch.setattr(NodeResolutionPipe, "resolve_selectors", resolver)
    locator = MagicMock(spec=Locator)
    page.locator.return_value = locator
    locator.count = AsyncMock(return_value=1)
    locator.evaluate.return_value = False
    assert await session.locate(ClickAction(id="B1")) is locator
    result = await session.aexecute(ClickAction(id="B1"), raise_on_failure=True)
    assert result.success
    assert resolver.await_count == 2
    locator.click.assert_awaited_once()

    monkeypatch.setattr(CaptchaHandler, "is_available", False)
    with pytest.raises(CaptchaSolverNotAvailableError):
        NotteSession(window=window, solve_captchas=True)
    handler = AsyncMock(return_value=True)
    monkeypatch.setattr(CaptchaHandler, "is_available", True)
    monkeypatch.setattr(CaptchaHandler, "handle_captchas", handler)
    assert NotteSession(window=window, solve_captchas=True).window is window
    action = CaptchaSolveAction()
    assert (await session.aexecute(action, raise_on_failure=True)).success
    handler.assert_awaited_once_with(window, action)


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
