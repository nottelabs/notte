import socket
from collections.abc import AsyncIterator
from contextlib import closing

import pytest
import pytest_asyncio
from aiohttp import web
from notte_browser.session import NotteSession
from notte_core.actions import CheckAction

PAGE = '<input type="checkbox" id="analytics" checked aria-label="Analytics">'


@pytest_asyncio.fixture(loop_scope="function")
async def site() -> AsyncIterator[str]:
    async def consent(_request: web.Request) -> web.Response:
        return web.Response(text=PAGE, content_type="text/html")

    app = web.Application()
    app.router.add_get("/consent", consent)
    runner = web.AppRunner(app)
    await runner.setup()
    with closing(socket.socket()) as server_socket:
        server_socket.bind(("127.0.0.1", 0))
        server_socket.listen()
        await web.SockSite(runner, server_socket).start()
        try:
            yield f"http://127.0.0.1:{server_socket.getsockname()[1]}/consent"
        finally:
            await runner.cleanup()


def test_check_message_says_whether_the_box_was_checked_or_unchecked() -> None:
    assert CheckAction(id="I1", value=True).execution_message() == "Checked the checkbox"
    assert CheckAction(id="I1", value=False).execution_message() == "Unchecked the checkbox"
    labelled = CheckAction(id="I1", value=False, text_label="Analytics")
    assert labelled.execution_message() == "Unchecked the checkbox 'Analytics'"


@pytest.mark.asyncio
async def test_unchecking_a_checked_box_says_unchecked(site: str) -> None:
    async with NotteSession(headless=True) as session:
        _ = await session.aexecute(type="goto", url=site)
        observation = await session.aobserve()
        [box] = observation.space.interaction_actions

        result = await session.aexecute(type="check", id=box.id, value=False)
        assert result.success, result.message
        assert result.message is not None and result.message.startswith("Unchecked the checkbox")
        assert not await session.window.page.is_checked("#analytics")

        result = await session.aexecute(type="check", id=box.id, value=True)
        assert result.message is not None and result.message.startswith("Checked the checkbox")
        assert await session.window.page.is_checked("#analytics")
