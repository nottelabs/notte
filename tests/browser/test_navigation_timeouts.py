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
    response.request.url = page.url
    response.request.redirected_from = None
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
async def test_committed_navigation_keeps_best_effort_load_wait() -> None:
    page = MagicMock()
    page.url = "https://example.com"
    page.is_closed.return_value = False
    response = make_response(page)
    page.goto = AsyncMock(return_value=response)
    window = make_window(page)

    with patch.object(BrowserWindow, "long_wait", new_callable=AsyncMock) as long_wait:
        await window.goto_and_wait("https://example.com")

    page.goto.assert_awaited_once_with("https://example.com", timeout=10000, wait_until="commit")
    long_wait.assert_awaited_once()
    assert window.goto_response is response


@pytest.mark.asyncio
async def test_late_response_from_previous_navigation_does_not_affect_next_timeout() -> None:
    page = MagicMock()
    page.url = "https://example.com"
    page.is_closed.return_value = False
    call_count = 0

    late_response = make_response(page)
    late_response.request.url = "https://first.example.com"

    def timeout_with_late_response(_url: str, **_kwargs: object) -> None:
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            window._record_navigation_response(late_response)
        raise PlaywrightTimeoutError("navigation timed out")

    page.goto = AsyncMock(side_effect=timeout_with_late_response)
    window = make_window(page)

    with pytest.raises(PageLoadingError):
        await window.goto_and_wait("https://first.example.com")

    window._record_navigation_response(late_response)
    assert window.goto_response is late_response

    with pytest.raises(PageLoadingError):
        await window.goto_and_wait("https://second.example.com")


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
    replacement_page.goto = AsyncMock(return_value=response)

    with patch.object(BrowserWindow, "long_wait", new_callable=AsyncMock) as long_wait:
        await window.goto_and_wait("https://replacement.example.com")

    assert resource.page is replacement_page
    replacement_page.on.assert_any_call("response", window._record_navigation_response)
    assert window.goto_response is response
    long_wait.assert_awaited_once()
