"""A goto whose page does not load in time logs what it still waited for: the document's ready state and the requests
in flight (type, host, age), never their paths or queries."""

import asyncio
import socket
from collections.abc import AsyncIterator, Iterator
from contextlib import closing, contextmanager
from unittest.mock import AsyncMock, patch

import notte_browser.execution as execution_module
import notte_browser.settle as settle_module
import notte_browser.window as window_module
import pytest
import pytest_asyncio
from aiohttp import web
from notte_browser.errors import PageLoadingError
from notte_browser.session import NotteSession
from notte_core.config import config
from notte_core.logging import logger

# An inline script waits for the stylesheets before it: while the stylesheet hangs, the parser stops above the table.
BLOCKED_PAGE = """<html><head><link rel="stylesheet" href="/blocking.css?token=secret-value"></head>
<body><h1>Navigation</h1><script>document.title = "parsed"</script><table id="rows"><tr><td>Row</td></tr></table>
</body></html>"""
# Loads at once, then keeps a fetch open: the goto's settle runs out of time on a page that has loaded.
POLLING_PAGE = """<html><body><h1>Loaded</h1>
<script>addEventListener("load", () => fetch("/hang?token=secret-value"))</script></body></html>"""

GOTO_TIMEOUT_MS = 1_500


@pytest_asyncio.fixture(loop_scope="function")
async def site() -> AsyncIterator[str]:
    release = asyncio.Event()

    async def blocked(_request: web.Request) -> web.Response:
        return web.Response(text=BLOCKED_PAGE, content_type="text/html")

    async def polling(_request: web.Request) -> web.Response:
        return web.Response(text=POLLING_PAGE, content_type="text/html")

    async def hang(_request: web.Request) -> web.Response:
        await release.wait()
        return web.Response(text="", content_type="text/css")

    app = web.Application()
    app.router.add_get("/blocked", blocked)
    app.router.add_get("/polling", polling)
    app.router.add_get("/blocking.css", hang)
    app.router.add_get("/hang", hang)
    app.router.add_get("/never", hang)
    runner = web.AppRunner(app)
    await runner.setup()
    with closing(socket.socket()) as server_socket:
        server_socket.bind(("127.0.0.1", 0))
        server_socket.listen()
        port = server_socket.getsockname()[1]
        try:
            await web.SockSite(runner, server_socket).start()
            yield f"http://127.0.0.1:{port}"
        finally:
            release.set()
            await runner.cleanup()


@pytest_asyncio.fixture(loop_scope="function")
async def session() -> AsyncIterator[NotteSession]:
    async with NotteSession(headless=True) as session:
        yield session


@contextmanager
def short_goto_timeout() -> Iterator[None]:
    test_config = config.model_copy(update={"timeout_goto_ms": GOTO_TIMEOUT_MS})
    previous = (window_module.config, settle_module.config, execution_module.config)
    window_module.config = settle_module.config = execution_module.config = test_config
    try:
        yield
    finally:
        window_module.config, settle_module.config, execution_module.config = previous


@contextmanager
def warnings() -> Iterator[list[str]]:
    records: list[str] = []
    handler_id = logger.add(lambda message: records.append(str(message)), level="WARNING", format="{message}")
    try:
        yield records
    finally:
        logger.remove(handler_id)


def stalled(records: list[str]) -> list[str]:
    return [record for record in records if "Goto for url=" in record]


@pytest.mark.asyncio
async def test_a_goto_waiting_for_domcontentloaded_logs_the_stylesheet_that_holds_the_parser(
    session: NotteSession, site: str
) -> None:
    with short_goto_timeout(), warnings() as records:
        result = await session.aexecute(type="goto", url=f"{site}/blocked", wait_until="domcontentloaded")
    assert result.success
    [line] = stalled(records)
    assert "timed out waiting for domcontentloaded" in line
    assert "document loading" in line
    assert "1 request in flight: stylesheet 127.0.0.1 " in line
    assert "blocking.css" not in line
    assert "secret-value" not in line


@pytest.mark.asyncio
async def test_a_default_goto_logs_why_its_page_did_not_load(session: NotteSession, site: str) -> None:
    with short_goto_timeout(), warnings() as records:
        result = await session.aexecute(type="goto", url=f"{site}/blocked")
    assert result.success
    [line] = stalled(records)
    assert f"did not load within {GOTO_TIMEOUT_MS} ms" in line
    assert "document loading" in line
    assert "stylesheet 127.0.0.1 " in line
    assert "secret-value" not in line


@pytest.mark.asyncio
async def test_a_default_goto_whose_page_loaded_but_keeps_a_request_open_logs_nothing(
    session: NotteSession, site: str
) -> None:
    log_stalled_goto = AsyncMock(side_effect=execution_module._log_stalled_goto)  # pyright: ignore[reportPrivateUsage]
    with (
        short_goto_timeout(),
        warnings() as records,
        patch.object(execution_module, "_log_stalled_goto", log_stalled_goto),
    ):
        result = await session.aexecute(type="goto", url=f"{site}/polling")
    assert result.success
    # the settle ran out of time on the open fetch, and the page had loaded
    log_stalled_goto.assert_awaited_once()
    assert stalled(records) == []


@pytest.mark.asyncio
async def test_a_goto_whose_document_never_commits_logs_the_document_request(session: NotteSession, site: str) -> None:
    with short_goto_timeout(), warnings() as records, pytest.raises(PageLoadingError):
        await session.window.goto_and_wait(f"{site}/never?token=secret-value")
    [line] = stalled(records)
    assert "timed out before the main document committed" in line
    assert "1 request in flight: document 127.0.0.1 " in line
    assert "secret-value" not in line.split("(", 1)[1]
