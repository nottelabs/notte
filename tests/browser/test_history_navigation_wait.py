"""`go_back` / `go_forward` wait for a page load only when the history navigation loads a page."""

import asyncio
import socket
import time
from collections.abc import AsyncIterator
from contextlib import closing

import pytest
import pytest_asyncio
from aiohttp import web
from notte_browser.session import NotteSession
from notte_core.config import config

# Records in the DOM, which every script world shares, whether the page was restored from the back-forward cache.
PAGESHOW = (
    "<script>addEventListener('pageshow', e => { document.documentElement.dataset.restored = e.persisted })</script>"
)
RESTORED = "document.documentElement.dataset.restored"
# Delays the load event of every page that shows the image; not stored, so a page load fetches it again.
SLOW_IMAGE_S = 1.5


@pytest_asyncio.fixture(loop_scope="function")
async def two_page_site() -> AsyncIterator[str]:
    async def page_a(_request: web.Request) -> web.Response:
        return web.Response(text=f'{PAGESHOW}<h1>A</h1><a href="/b">to b</a>', content_type="text/html")

    async def page_b(_request: web.Request) -> web.Response:
        return web.Response(text=f"{PAGESHOW}<h1>B</h1>", content_type="text/html")

    async def slow_page(_request: web.Request) -> web.Response:
        return web.Response(text=f'{PAGESHOW}<h1>slow</h1><img src="/slow.png">', content_type="text/html")

    async def slow_image(_request: web.Request) -> web.Response:
        await asyncio.sleep(SLOW_IMAGE_S)
        return web.Response(status=404, headers={"Cache-Control": "no-store"})

    app = web.Application()
    app.router.add_get("/a", page_a)
    app.router.add_get("/b", page_b)
    app.router.add_get("/slow", slow_page)
    app.router.add_get("/slow.png", slow_image)
    runner = web.AppRunner(app)
    await runner.setup()
    with closing(socket.socket()) as server_socket:
        server_socket.bind(("127.0.0.1", 0))
        server_socket.listen()
        site = web.SockSite(runner, server_socket)
        await site.start()
        try:
            yield f"http://127.0.0.1:{server_socket.getsockname()[1]}"
        finally:
            await runner.cleanup()


async def timed_history_navigation(session: NotteSession, action_type: str) -> float:
    start = time.monotonic()
    result = await session.aexecute(type=action_type)
    assert result.success, result.message
    return time.monotonic() - start


@pytest.mark.asyncio
async def test_back_and_forward_from_the_back_forward_cache_skip_the_load_wait(two_page_site: str) -> None:
    async with NotteSession(headless=True) as session:
        _ = await session.aexecute(type="goto", url=f"{two_page_site}/a")
        _ = await session.aexecute(type="goto", url=f"{two_page_site}/b")

        elapsed_s = await timed_history_navigation(session, "go_back")
        assert session.window.page.url == f"{two_page_site}/a"
        assert await session.window.page.evaluate(RESTORED) == "true"
        # A restore fires no new load event, so waiting for one would take the whole navigation timeout.
        assert elapsed_s < 2 < config.timeout_goto_ms / 1000

        elapsed_s = await timed_history_navigation(session, "go_forward")
        assert session.window.page.url == f"{two_page_site}/b"
        assert await session.window.page.evaluate(RESTORED) == "true"
        assert elapsed_s < 2


@pytest.mark.asyncio
async def test_back_that_loads_the_page_again_waits_for_load(two_page_site: str) -> None:
    async with NotteSession(headless=True, chrome_args=["--disable-back-forward-cache"]) as session:
        _ = await session.aexecute(type="goto", url=f"{two_page_site}/slow")
        _ = await session.aexecute(type="goto", url=f"{two_page_site}/b")

        elapsed_s = await timed_history_navigation(session, "go_back")
        assert session.window.page.url == f"{two_page_site}/slow"
        assert await session.window.page.evaluate(f"[document.readyState, {RESTORED}]") == ["complete", "false"]
        assert SLOW_IMAGE_S <= elapsed_s < config.timeout_goto_ms / 1000
