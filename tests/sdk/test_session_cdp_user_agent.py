"""`session.page` sends the SDK's User-Agent on the CDP WebSocket upgrade, with the real Playwright driver."""

import socket
import threading
from collections.abc import Iterator
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from notte_sdk.client_info import client_user_agent
from notte_sdk.endpoints import sessions
from notte_sdk.endpoints.sessions import AsyncRemoteSession, RemoteSession

_GITHUB = ("GITHUB_ACTIONS", "GITHUB_REPOSITORY", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "GITHUB_JOB")
_FORBIDDEN = b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"


@pytest.fixture(autouse=True)
def github_job(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _GITHUB:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_REPOSITORY", "acme/shop")
    monkeypatch.setenv("GITHUB_JOB", "e2e")
    monkeypatch.delenv("NOTTE_AUTH_CAPABILITY", raising=False)


@pytest.fixture
def server() -> Iterator[tuple[int, list[dict[str, str]]]]:
    """A local server that records each WebSocket upgrade request's headers and answers 403."""
    listener = socket.create_server(("127.0.0.1", 0))
    upgrades: list[dict[str, str]] = []

    def accept() -> None:
        while True:
            try:
                connection, _ = listener.accept()
            except OSError:
                return
            with connection:
                request = b""
                while b"\r\n\r\n" not in request:
                    chunk = connection.recv(65536)
                    if not chunk:
                        break
                    request += chunk
                lines = request.decode().split("\r\n\r\n", 1)[0].split("\r\n")[1:]
                upgrades.append({k.strip().lower(): v.strip() for k, _, v in (line.partition(":") for line in lines)})
                connection.sendall(_FORBIDDEN)

    threading.Thread(target=accept, daemon=True).start()
    yield listener.getsockname()[1], upgrades
    listener.close()


def _session(
    cls: type[RemoteSession] | type[AsyncRemoteSession], port: int, cdp_url: str | None
) -> RemoteSession | AsyncRemoteSession:
    session = object.__new__(cls)
    session.request = SimpleNamespace(cdp_url=cdp_url)
    session.client = SimpleNamespace(server_url=f"http://127.0.0.1:{port}", REQUEST_ORIGIN="sdk-python")
    session._playwright_browser = None
    session._playwright_context = None
    session._playwright_page = None
    session._async_playwright_browser = None
    session._async_playwright_context = None
    session._async_playwright_page = None
    url = cdp_url or f"ws://127.0.0.1:{port}/sessions/s/cdp"
    asynchronous = cls is AsyncRemoteSession
    session.cdp_url = AsyncMock(return_value=url) if asynchronous else MagicMock(return_value=url)
    session.status = (AsyncMock if asynchronous else MagicMock)(side_effect=Exception("status unavailable"))
    return session


def test_sync_page_sends_the_sdk_user_agent(server: tuple[int, list[dict[str, str]]]) -> None:
    port, upgrades = server
    session = _session(RemoteSession, port, None)
    try:
        with pytest.raises(RuntimeError, match="Failed to access the playwright page") as raised:
            _ = session.page
    finally:
        if session._playwright_context is not None:  # pyright: ignore [reportPrivateUsage]
            session._playwright_context.stop()  # pyright: ignore [reportPrivateUsage]

    assert "403 Forbidden" in str(raised.value.__cause__)

    assert len(upgrades) == 1
    assert upgrades[0]["user-agent"] == client_user_agent()
    assert upgrades[0]["user-agent"].endswith(" github-actions (repo=acme/shop; job=e2e)")
    assert upgrades[0]["x-notte-request-origin"] == "sdk-python"


@pytest.mark.asyncio
async def test_async_page_sends_the_sdk_user_agent(server: tuple[int, list[dict[str, str]]]) -> None:
    port, upgrades = server
    session = _session(AsyncRemoteSession, port, None)
    try:
        with pytest.raises(RuntimeError, match="Failed to access the async playwright page") as raised:
            _ = await session.page
    finally:
        await sessions._close_async_playwright(session)  # pyright: ignore [reportPrivateUsage]

    assert "403 Forbidden" in str(raised.value.__cause__)
    assert len(upgrades) == 1
    assert upgrades[0]["user-agent"] == client_user_agent()


def test_a_callers_own_cdp_endpoint_keeps_playwrights_user_agent(server: tuple[int, list[dict[str, str]]]) -> None:
    port, upgrades = server
    session = _session(RemoteSession, port, f"ws://127.0.0.1:{port}/own-browser")
    try:
        with pytest.raises(RuntimeError, match="Failed to access the playwright page") as raised:
            _ = session.page
    finally:
        if session._playwright_context is not None:  # pyright: ignore [reportPrivateUsage]
            session._playwright_context.stop()  # pyright: ignore [reportPrivateUsage]

    assert "403 Forbidden" in str(raised.value.__cause__)

    assert len(upgrades) == 1
    assert upgrades[0]["user-agent"].startswith("Playwright/")
    assert "x-notte-request-origin" not in upgrades[0]
