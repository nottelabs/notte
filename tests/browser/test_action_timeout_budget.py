"""An interaction's `timeout` bounds the interaction itself, not the page load it triggers."""

import asyncio
import socket
import time
from collections.abc import AsyncIterator
from contextlib import closing

import pytest
import pytest_asyncio
from aiohttp import web
from notte_browser.session import NotteSession
from notte_core.actions import (
    CheckAction,
    ClickAction,
    FallbackFillAction,
    FillAction,
    MultiFactorFillAction,
    SelectDropdownOptionAction,
)
from notte_core.actions.actions import InteractionAction

# The image keeps the next page from reaching `networkidle` for this long.
SLOW_SUBRESOURCE_S = 2.5


@pytest_asyncio.fixture(loop_scope="function")
async def slow_site() -> AsyncIterator[str]:
    async def start(_request: web.Request) -> web.Response:
        return web.Response(text='<a id="next" href="/next">next</a>', content_type="text/html")

    async def next_page(_request: web.Request) -> web.Response:
        # Navigation must remain outside the click budget even before the response commits.
        await asyncio.sleep(1.5)
        return web.Response(text='<h1 id="done">next</h1><img src="/slow.png">', content_type="text/html")

    async def slow_image(_request: web.Request) -> web.Response:
        await asyncio.sleep(SLOW_SUBRESOURCE_S)
        return web.Response(status=404)

    app = web.Application()
    app.router.add_get("/", start)
    app.router.add_get("/next", next_page)
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


@pytest.mark.asyncio
async def test_click_that_navigates_to_a_slow_page_succeeds(slow_site: str) -> None:
    async with NotteSession(headless=True) as session:
        _ = await session.aexecute(type="goto", url=f"{slow_site}/", wait_until="load")

        start = time.monotonic()
        result = await session.aexecute(ClickAction(selector="#next", timeout=1000), raise_on_failure=False)

        assert result.success, result.message
        assert session.window.page.url == f"{slow_site}/next"
        # the click returned within its budget; the settle wait for the slow page ran after it
        assert time.monotonic() - start > 1.0


@pytest.mark.asyncio
async def test_click_falls_back_to_a_js_click_within_its_budget() -> None:
    async with NotteSession(headless=True) as session:
        await session.window.page.set_content("""
            <button id="target" onclick="document.body.dataset.clicked = 'yes'">Apply</button>
            <div style="position: fixed; inset: 0; background: white"></div>
        """)

        result = await session.aexecute(ClickAction(selector="#target", timeout=1500), raise_on_failure=False)

        assert result.success, result.message
        assert await session.window.page.evaluate("document.body.dataset.clicked") == "yes"


SHOWN_LATE = """
<input id="input" style="display: none">
<input id="checkbox" type="checkbox" style="display: none">
<select id="select" style="display: none"><option>a</option><option>b</option></select>
<script>setTimeout(() => document.querySelectorAll("[style]").forEach((el) => el.style.display = ""), 800)</script>
"""


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "action",
    [
        FillAction(selector="#input", value="hello", timeout=5000),
        MultiFactorFillAction(selector="#input", value="123", timeout=5000),
        FallbackFillAction(selector="#input", value="hello", timeout=5000),
        CheckAction(selector="#checkbox", value=True, timeout=5000),
        SelectDropdownOptionAction(selector="#select", value="b", timeout=5000),
    ],
    ids=lambda action: action.type,
)
async def test_interactions_wait_up_to_their_own_timeout(action: InteractionAction) -> None:
    async with NotteSession(headless=True) as session:
        await session.window.page.set_content(SHOWN_LATE)
        # far below the action's timeout and the element's delay: only `action.timeout` may apply
        session.window.page.set_default_timeout(200)

        result = await session.aexecute(action, raise_on_failure=False)

        assert result.success, result.message
