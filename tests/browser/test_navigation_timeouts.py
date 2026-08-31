from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from notte_browser.errors import PageLoadingError
from notte_browser.playwright_async_api import TimeoutError as PlaywrightTimeoutError
from notte_browser.window import BrowserWindow


def make_window(page: MagicMock) -> BrowserWindow:
    resource = MagicMock()
    resource.page = page
    return BrowserWindow.model_construct(
        resource=resource,
        screenshot_mask=None,
        on_close=None,
        page_callbacks={},
        goto_response=None,
    )


@pytest.mark.asyncio
async def test_goto_timeout_without_response_is_not_reported_as_success() -> None:
    page = MagicMock()
    page.url = "https://www.duckduckgo.com"
    page.is_closed.return_value = False
    page.goto = AsyncMock(side_effect=PlaywrightTimeoutError("navigation timed out"))
    window = make_window(page)

    with (
        patch.object(BrowserWindow, "long_wait", new_callable=AsyncMock) as long_wait,
        patch.object(BrowserWindow, "short_wait", new_callable=AsyncMock) as short_wait,
        pytest.raises(PageLoadingError),
    ):
        await window.goto_and_wait("https://www.duckduckgo.com")

    long_wait.assert_not_awaited()
    short_wait.assert_not_awaited()


@pytest.mark.asyncio
async def test_goto_timeout_with_response_keeps_best_effort_load_wait() -> None:
    response = MagicMock()
    response.status = 200
    response.status_text = "OK"

    page = MagicMock()
    page.url = "https://example.com"
    page.is_closed.return_value = False

    def capture_response(_url: str, **_kwargs: object) -> None:
        window.goto_response = response
        raise PlaywrightTimeoutError("load event timed out")

    page.goto = AsyncMock(side_effect=capture_response)
    window = make_window(page)

    with (
        patch.object(BrowserWindow, "long_wait", new_callable=AsyncMock) as long_wait,
        patch.object(BrowserWindow, "short_wait", new_callable=AsyncMock) as short_wait,
    ):
        await window.goto_and_wait("https://example.com")

    long_wait.assert_awaited_once()
    short_wait.assert_awaited_once()
