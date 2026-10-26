"""`go_back` / `go_forward` fail when the tab has no page there, instead of reporting a navigation that did not happen."""

import socket
from collections.abc import AsyncIterator
from contextlib import closing

import pytest
import pytest_asyncio
from aiohttp import web
from notte_browser.session import NotteSession


@pytest_asyncio.fixture(loop_scope="function")
async def site() -> AsyncIterator[str]:
    async def home(_request: web.Request) -> web.Response:
        return web.Response(text='<h1>Home</h1><a href="/help" target="_blank">Open help</a>', content_type="text/html")

    async def help_page(_request: web.Request) -> web.Response:
        return web.Response(text="<h1>Help</h1><p>The code is 4821.</p>", content_type="text/html")

    app = web.Application()
    app.router.add_get("/home", home)
    app.router.add_get("/help", help_page)
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
async def test_back_in_a_tab_opened_by_a_link_fails(site: str) -> None:
    async with NotteSession(headless=True) as session:
        _ = await session.aexecute(type="goto", url=f"{site}/home")
        observation = await session.aobserve()
        link = next(action for action in observation.space.interaction_actions if action.text_label == "Open help")
        _ = await session.aexecute(type="click", id=link.id)
        assert session.window.page.url == f"{site}/help"

        result = await session.aexecute(type="go_back", raise_on_failure=False)
        assert not result.success
        assert result.message == "Cannot go back: this tab has no previous page in its history."
        assert session.window.page.url == f"{site}/help"

        result = await session.aexecute(type="go_forward", raise_on_failure=False)
        assert not result.success
        assert result.message == "Cannot go forward: this tab has no next page in its history."


@pytest.mark.asyncio
@pytest.mark.parametrize("entry", ["history.pushState({modal: true}, '', location.href)", "location.hash = 'details'"])
async def test_back_within_the_document_succeeds(site: str, entry: str) -> None:
    async with NotteSession(headless=True) as session:
        _ = await session.aexecute(type="goto", url=f"{site}/home")
        await session.window.page.evaluate(entry)

        result = await session.aexecute(type="go_back", raise_on_failure=False)
        assert result.success, result.message
        assert session.window.page.url == f"{site}/home"

        result = await session.aexecute(type="go_forward", raise_on_failure=False)
        assert result.success, result.message


@pytest.mark.asyncio
async def test_back_to_the_previous_document_succeeds(site: str) -> None:
    async with NotteSession(headless=True) as session:
        _ = await session.aexecute(type="goto", url=f"{site}/help")
        _ = await session.aexecute(type="goto", url=f"{site}/home")

        result = await session.aexecute(type="go_back", raise_on_failure=False)
        assert result.success, result.message
        assert session.window.page.url == f"{site}/help"


@pytest.mark.asyncio
async def test_back_in_a_blank_tab_fails_without_moving(site: str) -> None:
    async with NotteSession(headless=True) as session:
        assert session.window.page.url == "about:blank"
        result = await session.aexecute(type="go_back", raise_on_failure=False)
        assert not result.success
        assert result.message == "Cannot go back: this tab has no previous page in its history."


@pytest.mark.asyncio
async def test_a_failed_back_leaves_no_listener_behind(site: str) -> None:
    async with NotteSession(headless=True) as session:
        _ = await session.aexecute(type="goto", url=f"{site}/home")
        observation = await session.aobserve()
        link = next(action for action in observation.space.interaction_actions if action.text_label == "Open help")
        _ = await session.aexecute(type="click", id=link.id)
        page = session.window.page
        assert page.url == f"{site}/help"
        await page.evaluate("""() => {
            window.popstateListeners = 0;
            const add = EventTarget.prototype.addEventListener, remove = EventTarget.prototype.removeEventListener;
            EventTarget.prototype.addEventListener = function (type, ...rest) {
                if (type === 'popstate') window.popstateListeners++;
                return add.call(this, type, ...rest);
            };
            EventTarget.prototype.removeEventListener = function (type, ...rest) {
                if (type === 'popstate') window.popstateListeners--;
                return remove.call(this, type, ...rest);
            };
        }""")
        for _ in range(3):
            assert not (await session.aexecute(type="go_back", raise_on_failure=False)).success
        assert await page.evaluate("window.popstateListeners") == 0
