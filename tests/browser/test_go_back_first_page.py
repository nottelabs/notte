"""`go_back` on the first page a tab opened fails, instead of leaving it for the blank page the tab started on.

A session's tab is created on `about:blank`, so after the first `goto` its history has a previous entry. Going back
loaded that blank page: the page and what was typed in it were gone, and the result was "Failed to load page".
"""

import socket
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import closing

import pytest
import pytest_asyncio
from aiohttp import web
from notte_browser.session import NotteSession


@pytest_asyncio.fixture(loop_scope="function")
async def site() -> AsyncIterator[str]:
    def page(title: str) -> Callable[[web.Request], Awaitable[web.Response]]:
        async def handler(_request: web.Request) -> web.Response:
            return web.Response(text=f"<h1>{title}</h1><input id='name'>", content_type="text/html")

        return handler

    app = web.Application()
    for name, title in [("shipping", "Shipping"), ("review", "Review"), ("home", "Home"), ("help", "Help")]:
        app.router.add_get(f"/{name}", page(title))
    runner = web.AppRunner(app)
    await runner.setup()
    with closing(socket.socket()) as server_socket:
        server_socket.bind(("127.0.0.1", 0))
        server_socket.listen()
        await web.SockSite(runner, server_socket).start()
        try:
            yield f"http://127.0.0.1:{server_socket.getsockname()[1]}"
        finally:
            await runner.cleanup()


@pytest.mark.asyncio
async def test_back_on_the_first_page_of_the_session_fails_and_keeps_the_page(site: str) -> None:
    async with NotteSession(headless=True) as session:
        _ = await session.aexecute(type="goto", url=f"{site}/shipping")
        await session.window.page.fill("#name", "Ada")

        result = await session.aexecute(type="go_back", raise_on_failure=False)
        assert not result.success
        assert result.message == "Cannot go back: this is the first page this tab opened."
        assert session.window.page.url == f"{site}/shipping"
        assert await session.window.page.input_value("#name") == "Ada"


@pytest.mark.asyncio
async def test_back_on_the_first_page_of_a_new_tab_fails(site: str) -> None:
    async with NotteSession(headless=True) as session:
        _ = await session.aexecute(type="goto", url=f"{site}/home")
        _ = await session.aexecute(type="goto_new_tab", url=f"{site}/help")

        result = await session.aexecute(type="go_back", raise_on_failure=False)
        assert not result.success
        assert session.window.page.url == f"{site}/help"


@pytest.mark.asyncio
async def test_back_to_a_page_the_tab_opened_succeeds(site: str) -> None:
    async with NotteSession(headless=True) as session:
        _ = await session.aexecute(type="goto", url=f"{site}/shipping")
        _ = await session.aexecute(type="goto", url=f"{site}/review")

        result = await session.aexecute(type="go_back", raise_on_failure=False)
        assert result.success, result.message
        assert session.window.page.url == f"{site}/shipping"

        # and from there, the first page: no further back
        result = await session.aexecute(type="go_back", raise_on_failure=False)
        assert not result.success
        assert session.window.page.url == f"{site}/shipping"
