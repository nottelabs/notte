from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from notte_sdk.endpoints import sessions
from notte_sdk.endpoints.sessions import RemoteSession

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
    session._playwright_observed_pages = set()
    session._playwright_observed_contexts = set()
    session._playwright_cleanup_in_progress = False
    session.cdp_url = MagicMock(return_value=cdp_url)
    session.stop = MagicMock()
    return session


@pytest.fixture
def lifecycle_logs() -> Iterator[list[tuple[str, str]]]:
    records: list[tuple[str, str]] = []

    def sink(message: object) -> None:
        record = message.record  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType, reportUnknownVariableType]
        if record["message"].startswith("[Session Playwright]"):  # pyright: ignore[reportUnknownMemberType]
            records.append((record["level"].name, record["message"]))  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]

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

    before_exit = len(lifecycle_logs)
    session.__exit__(None, None, None)
    events = _events(lifecycle_logs[before_exit:])
    assert ("DEBUG", "sdk_playwright_browser_disconnected") in events
    assert all(level == "DEBUG" for level, _ in events)
    session.stop.assert_called_once_with(close_reason="manual")

    assert any(html.as_uri() in message for _, message in lifecycle_logs)
    assert not any("secret" in message for _, message in lifecycle_logs)
