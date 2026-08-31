from collections.abc import Callable
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from notte_browser.errors import PageLoadingError
from notte_browser.playwright_async_api import TimeoutError as PlaywrightTimeoutError
from notte_browser.window import BrowserResource, BrowserWindow


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


def make_response(page: MagicMock, *, status: int = 200) -> MagicMock:
    response = MagicMock()
    response.status = status
    response.status_text = "OK"
    response.request.is_navigation_request.return_value = True
    response.request.frame = page.main_frame
    return response


@pytest.mark.parametrize(
    ("is_navigation", "is_main_frame", "status"),
    [
        (False, True, 200),
        (True, False, 200),
        (True, True, 302),
        (True, True, 307),
    ],
)
def test_only_final_main_document_response_is_recorded(is_navigation: bool, is_main_frame: bool, status: int) -> None:
    page = MagicMock()
    response = MagicMock()
    response.status = status
    response.request.is_navigation_request.return_value = is_navigation
    response.request.frame = page.main_frame if is_main_frame else MagicMock()
    window = make_window(page)

    window._record_navigation_response(response)

    assert window.goto_response is None


def test_final_main_document_response_is_recorded() -> None:
    page = MagicMock()
    response = make_response(page)
    window = make_window(page)

    window._record_navigation_response(response)

    assert window.goto_response is response


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
    page = MagicMock()
    page.url = "https://example.com"
    page.is_closed.return_value = False
    response = make_response(page)
    response_callback: Callable[[MagicMock], None] | None = None

    def register_response_callback(_event: str, callback: Callable[[MagicMock], None]) -> None:
        nonlocal response_callback
        response_callback = callback

    def capture_response(_url: str, **_kwargs: object) -> None:
        assert callable(response_callback)
        response_callback(response)
        raise PlaywrightTimeoutError("load event timed out")

    page.on.side_effect = register_response_callback
    page.goto = AsyncMock(side_effect=capture_response)
    window = make_window(page)

    with (
        patch.object(BrowserWindow, "long_wait", new_callable=AsyncMock) as long_wait,
        patch.object(BrowserWindow, "short_wait", new_callable=AsyncMock) as short_wait,
    ):
        await window.goto_and_wait("https://example.com")

    long_wait.assert_awaited_once()
    short_wait.assert_awaited_once()
    page.remove_listener.assert_called_once_with("response", response_callback)


@pytest.mark.asyncio
async def test_late_response_from_previous_navigation_does_not_affect_next_timeout() -> None:
    page = MagicMock()
    page.url = "https://example.com"
    page.is_closed.return_value = False
    page.goto = AsyncMock(side_effect=PlaywrightTimeoutError("navigation timed out"))
    window = make_window(page)

    with pytest.raises(PageLoadingError):
        await window.goto_and_wait("https://first.example.com")

    late_response = make_response(page)
    window._record_navigation_response(late_response)
    assert window.goto_response is late_response

    with pytest.raises(PageLoadingError):
        await window.goto_and_wait("https://second.example.com")

    assert page.remove_listener.call_count == 2


@pytest.mark.asyncio
async def test_replacement_page_receives_persistent_and_attempt_response_callbacks() -> None:
    active_page = MagicMock()
    active_page.url = "https://closed.example.com"
    active_page.is_closed.return_value = False

    replacement_page = MagicMock()
    replacement_page.url = "https://replacement.example.com"
    replacement_page.is_closed.return_value = False
    active_page.context.pages = [replacement_page]

    resource = BrowserResource.model_construct(page=active_page, options=MagicMock())
    window = BrowserWindow(resource=resource)
    active_page.is_closed.return_value = True

    response = make_response(replacement_page)
    response_callbacks: list[Callable[[MagicMock], None]] = []

    def register_response_callback(_event: str, callback: Callable[[MagicMock], None]) -> None:
        response_callbacks.append(callback)

    def capture_response(_url: str, **_kwargs: object) -> None:
        for callback in response_callbacks:
            callback(response)
        raise PlaywrightTimeoutError("load event timed out")

    replacement_page.on.side_effect = register_response_callback
    replacement_page.goto = AsyncMock(side_effect=capture_response)

    with (
        patch.object(BrowserWindow, "long_wait", new_callable=AsyncMock) as long_wait,
        patch.object(BrowserWindow, "short_wait", new_callable=AsyncMock),
    ):
        await window.goto_and_wait("https://replacement.example.com")

    assert resource.page is replacement_page
    assert len(response_callbacks) == 2
    assert window.goto_response is response
    long_wait.assert_awaited_once()
