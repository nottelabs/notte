"""A `goto` that lands on a page served with an error status (a deny, rate-limit, challenge or error page) still
succeeds, and its message says what the main document answered. A 2xx page keeps the plain message."""

import asyncio
import socket
import time
from collections.abc import AsyncIterator
from contextlib import closing

import pytest
import pytest_asyncio
from aiohttp import web
from notte_browser.session import NotteSession
from notte_browser.window import document_answer
from notte_core.actions import GotoAction

DENY = "<html><head><title>Access Denied</title></head><body><h1>Access Denied</h1></body></html>"
HOME = '<html><head><title>Home</title></head><body><input id="q" placeholder="Search"><h1>Welcome</h1></body></html>'
# a script challenge: the first visit is refused with a page that reloads itself, the second visit is the page
CHALLENGE = (
    "<html><head><title>Just a moment...</title></head><body>Verifying<script>location.reload()</script></body></html>"
)
# the same, when the reload comes later than the goto's wait (the test reloads it by hand)
HELD_CHALLENGE = "<html><head><title>Just a moment...</title></head><body>Verifying you are human.</body></html>"
# an error page whose script never yields the main thread: it tells the server it is about to block, then blocks
BUSY = (
    "<html><head><title>Access Denied</title></head><body><script>"
    "var x = new XMLHttpRequest(); x.open('GET', '/busy-started', false); x.send(); while (true) {}"
    "</script></body></html>"
)

ERROR_PAGES = {
    403: ("Forbidden", "Access Denied"),
    404: ("Not Found", "Not Found"),
    429: ("Too Many Requests", "Too Many Requests"),
    503: ("Service Unavailable", "Service Unavailable"),
}


class Site:
    def __init__(self, url: str, busy_started: asyncio.Event) -> None:
        self.url: str = url
        # set when the busy page's script has entered its loop
        self.busy_started: asyncio.Event = busy_started


@pytest_asyncio.fixture(loop_scope="function")
async def site() -> AsyncIterator[Site]:
    visits: dict[str, int] = {}
    busy_started = asyncio.Event()

    async def ok(_request: web.Request) -> web.Response:
        return web.Response(text=HOME, content_type="text/html")

    async def error(request: web.Request) -> web.Response:
        status = int(request.match_info["status"])
        title = ERROR_PAGES[status][1]
        return web.Response(status=status, text=DENY.replace("Access Denied", title), content_type="text/html")

    def challenge(body: str):
        async def handler(request: web.Request) -> web.Response:
            visits[request.path] = visits.get(request.path, 0) + 1
            if visits[request.path] == 1:
                return web.Response(status=403, text=body, content_type="text/html")
            return web.Response(text=HOME, content_type="text/html")

        return handler

    async def busy(_request: web.Request) -> web.Response:
        return web.Response(status=403, text=BUSY, content_type="text/html")

    async def busy_start(_request: web.Request) -> web.Response:
        busy_started.set()
        return web.Response(status=204)

    app = web.Application()
    app.router.add_get("/ok", ok)
    app.router.add_get("/error/{status}", error)
    app.router.add_get("/challenge", challenge(CHALLENGE))
    app.router.add_get("/held-challenge", challenge(HELD_CHALLENGE))
    app.router.add_get("/busy", busy)
    app.router.add_get("/busy-started", busy_start)
    runner = web.AppRunner(app)
    await runner.setup()
    with closing(socket.socket()) as server_socket:
        server_socket.bind(("127.0.0.1", 0))
        server_socket.listen()
        web_site = web.SockSite(runner, server_socket)
        await web_site.start()
        try:
            yield Site(f"http://127.0.0.1:{server_socket.getsockname()[1]}", busy_started)
        finally:
            await runner.cleanup()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", sorted(ERROR_PAGES))
async def test_goto_on_an_error_page_succeeds_and_says_what_it_answered(site: Site, status: int) -> None:
    phrase, title = ERROR_PAGES[status]
    action = GotoAction(url=f"{site.url}/error/{status}")
    async with NotteSession(headless=True) as session:
        result = await session.aexecute(action, raise_on_failure=False)

    assert result.success, result.message
    assert result.message.startswith(action.execution_message() + ". ")
    assert f"HTTP {status} {phrase}" in result.message
    assert f'title "{title}"' in result.message


@pytest.mark.asyncio
async def test_goto_on_a_normal_page_keeps_the_plain_message(site: Site) -> None:
    action = GotoAction(url=f"{site.url}/ok")
    async with NotteSession(headless=True) as session:
        result = await session.aexecute(action, raise_on_failure=False)

    assert result.success
    assert result.message == action.execution_message()


@pytest.mark.asyncio
async def test_goto_new_tab_on_an_error_page_says_what_it_answered(site: Site) -> None:
    async with NotteSession(headless=True) as session:
        result = await session.aexecute(type="goto_new_tab", url=f"{site.url}/error/403", raise_on_failure=False)

    assert result.success, result.message
    assert "HTTP 403 Forbidden" in result.message


@pytest.mark.asyncio
async def test_another_tabs_error_status_is_not_reported_for_the_current_tab(site: Site) -> None:
    """The main-document response the window remembers is the last tab's: a tab switch followed by a goto to the
    current tab's own URL (which does not navigate) must not report the other tab's status with this tab's title."""
    home = GotoAction(url=f"{site.url}/ok")
    async with NotteSession(headless=True) as session:
        assert (await session.aexecute(home, raise_on_failure=False)).message == home.execution_message()
        denied = await session.aexecute(type="goto_new_tab", url=f"{site.url}/error/403", raise_on_failure=False)
        assert "HTTP 403 Forbidden" in denied.message
        assert (await session.aexecute(type="switch_tab", tab_index=0, raise_on_failure=False)).success

        result = await session.aexecute(home, raise_on_failure=False)
        assert await session.window.page.title() == "Home"
        assert result.success
        assert result.message == home.execution_message()

        # back on the denied tab, its own status is still reported, also when the goto does not navigate
        assert (await session.aexecute(type="switch_tab", tab_index=1, raise_on_failure=False)).success
        again = await session.aexecute(type="goto", url=f"{site.url}/error/403", raise_on_failure=False)
        assert "HTTP 403 Forbidden" in again.message
        assert 'title "Access Denied"' in again.message


@pytest.mark.asyncio
async def test_an_error_page_that_blocks_its_main_thread_is_reported_without_its_title(site: Site) -> None:
    """A title read on a page whose script never yields does not return: the status is reported without it, in
    bounded time, instead of holding the action."""
    async with NotteSession(headless=True) as session:
        await session.window.goto(f"{site.url}/busy", wait_until="commit")
        await asyncio.wait_for(site.busy_started.wait(), timeout=10)

        started = time.monotonic()
        answer = await asyncio.wait_for(session.window.main_document_answer(), timeout=30)
        elapsed = time.monotonic() - started

    assert answer is not None
    assert answer.startswith("The page answered HTTP 403 Forbidden:")
    assert "title" not in answer
    assert elapsed < 20, elapsed


@pytest.mark.asyncio
async def test_a_challenge_that_reloads_before_the_goto_returns_is_reported_as_the_page(site: Site) -> None:
    action = GotoAction(url=f"{site.url}/challenge")
    async with NotteSession(headless=True) as session:
        result = await session.aexecute(action, raise_on_failure=False)
        assert await session.window.page.title() == "Home"

    assert result.success
    assert result.message == action.execution_message()


@pytest.mark.asyncio
async def test_a_challenge_that_reloads_later_is_reported_and_the_script_goes_on(site: Site) -> None:
    """Why the error status fails no goto: a site that answers 403 with a script challenge, then serves the page,
    must keep working. The message carries the 403, the following actions find the page."""
    action = GotoAction(url=f"{site.url}/held-challenge")
    async with NotteSession(headless=True) as session:
        result = await session.aexecute(action, raise_on_failure=False)
        assert result.success
        assert "HTTP 403 Forbidden" in result.message
        assert 'title "Just a moment..."' in result.message

        # the challenge clears: the page reloads itself to the content
        _ = await session.window.page.reload(wait_until="load")
        filled = await session.aexecute(type="fill", selector="#q", value="trail", raise_on_failure=False)
        assert filled.success, filled.message
        assert await session.window.main_document_answer() is None


def test_document_answer_falls_back_to_the_standard_phrase() -> None:
    # HTTP/2 carries no reason phrase
    assert document_answer(403, "", None) == (
        "The page answered HTTP 403 Forbidden: it may be an error, deny or challenge page rather than the page's content."
    )
    assert document_answer(599, "", "Odd") == (
        'The page answered HTTP 599 with title "Odd": it may be an error, deny or challenge page rather than the page\'s content.'
    )
    assert document_answer(200, "OK", "Home") is None
    assert document_answer(304, "", None) is None
