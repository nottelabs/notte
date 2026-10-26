import weakref
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest
from notte_sdk.endpoints import sessions
from notte_sdk.endpoints.sessions import RemoteSession

if TYPE_CHECKING:
    from loguru import Message

from tests.integration.test_local_cdp_session import cdp_browser  # noqa: F401  # pyright: ignore[reportUnusedImport]


def _session_for(cdp_url: str) -> RemoteSession:
    session = object.__new__(RemoteSession)
    session.request = SimpleNamespace(cdp_url=None)
    session.client = SimpleNamespace(server_url="https://notte.example", REQUEST_ORIGIN="sdk-python")
    session.response = MagicMock(session_id="session-id")
    session._playwright_context = None
    session._playwright_browser = None
    session._playwright_page = None
    session._async_playwright_context = None
    session._async_playwright_browser = None
    session._async_playwright_page = None
    session._playwright_connection_generation = 0
    session._playwright_observed_pages = weakref.WeakSet()
    session._playwright_observed_contexts = weakref.WeakSet()
    session._playwright_cleanup_in_progress = False
    session.cdp_url = MagicMock(return_value=cdp_url)
    session.stop = MagicMock()
    return session


@pytest.fixture
def lifecycle_logs() -> Iterator[list[tuple[str, str]]]:
    records: list[tuple[str, str]] = []

    def sink(message: "Message") -> None:
        record = message.record
        if record["message"].startswith("[Session Playwright]"):
            records.append((record["level"].name, record["message"]))

    handler_id = sessions.logger.add(sink, level="DEBUG")
    try:
        yield records
    finally:
        sessions.logger.remove(handler_id)


def _events(records: list[tuple[str, str]]) -> list[tuple[str, str]]:
    return [(level, message.split(":", 1)[0].removeprefix("[Session Playwright] ")) for level, message in records]


def test_playwright_lifecycle_is_logged_against_real_browser(
    cdp_browser: str,  # noqa: F811
    lifecycle_logs: list[tuple[str, str]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    html = tmp_path / "page.html"
    _ = html.write_text("<title>lifecycle</title>")
    session = _session_for(cdp_browser)

    page = session.page
    _ = page.goto(f"{html.as_uri()}?token=secret-token#access_token=secret-fragment")
    assert _events(lifecycle_logs) == [("INFO", "sdk_playwright_connected")]

    popup = page.context.new_page()
    popup.close()
    assert session.page is page
    assert _events(lifecycle_logs)[1:] == [
        ("INFO", "sdk_playwright_page_created"),
        ("INFO", "sdk_playwright_page_closed"),
    ]

    page.close()
    assert session.page is page
    assert _events(lifecycle_logs)[3:] == [
        ("WARNING", "sdk_playwright_page_closed"),
        ("WARNING", "sdk_playwright_cached_page_unhealthy"),
    ]

    cleanup_popup = page.context.new_page()
    browser = page.context.browser
    assert browser is not None
    close_browser = browser.close

    def close_with_popup() -> None:
        cleanup_popup.close()
        close_browser()

    monkeypatch.setattr(browser, "close", close_with_popup)
    before_exit = len(lifecycle_logs)
    session.__exit__(None, None, None)
    events = _events(lifecycle_logs[before_exit:])
    assert events[0] == ("INFO", "sdk_playwright_session_stop_requested")
    assert ("DEBUG", "sdk_playwright_page_closed") in events[1:]
    assert ("DEBUG", "sdk_playwright_browser_disconnected") in events[1:]
    assert all(level == "DEBUG" for level, _ in events[1:])
    session.stop.assert_called_once_with(close_reason="manual")

    assert any("'url': 'file:'" in message for _, message in lifecycle_logs)
    assert not any(html.as_uri() in message for _, message in lifecycle_logs)
    assert not any("secret" in message for _, message in lifecycle_logs)
