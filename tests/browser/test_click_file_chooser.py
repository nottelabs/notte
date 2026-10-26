"""A click that opens a native file chooser chooses no file: it fails with a hint to upload the file instead."""

import asyncio
import socket
from collections.abc import AsyncIterator
from contextlib import closing
from unittest.mock import AsyncMock, MagicMock

import notte_browser.window as window_module
import pytest
import pytest_asyncio
from aiohttp import web
from notte_browser.execution import execute
from notte_browser.session import NotteSession
from notte_core.actions import ClickAction
from notte_core.errors import FileChooserOpenedError

PAGE = """
<style>
    #photo { position: absolute; width: 1px; height: 1px; opacity: 0 }
    label { cursor: pointer }
</style>
<label for="photo">Choose a photo</label>
<input type="file" id="photo">
<input type="file" id="document" style="display: none">
<button onclick="document.getElementById('document').click()">Browse files</button>
<input type="file" id="locked" style="display: none" onclick="event.preventDefault()">
<button onclick="document.getElementById('locked').click()">Locked</button>
<button onclick="this.textContent = 'Saved'">Save</button>
"""


@pytest_asyncio.fixture(loop_scope="function")
async def site() -> AsyncIterator[str]:
    async def upload(_request: web.Request) -> web.Response:
        return web.Response(text=PAGE, content_type="text/html")

    app = web.Application()
    app.router.add_get("/upload", upload)
    runner = web.AppRunner(app)
    await runner.setup()
    with closing(socket.socket()) as server_socket:
        server_socket.bind(("127.0.0.1", 0))
        server_socket.listen()
        await web.SockSite(runner, server_socket).start()
        try:
            yield f"http://127.0.0.1:{server_socket.getsockname()[1]}/upload"
        finally:
            await runner.cleanup()


@pytest.mark.asyncio
@pytest.mark.parametrize("wait_short_ms", [None, 0])
async def test_click_that_opens_a_file_chooser_fails(
    site: str, wait_short_ms: int | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    if wait_short_ms is not None:
        # no wait after the click (Playwright reports the chooser after the click has returned)
        config = window_module.config.model_copy(update={"wait_short_ms": wait_short_ms})
        monkeypatch.setattr(window_module, "config", config)
    async with NotteSession(headless=True) as session:
        _ = await session.aexecute(type="goto", url=site)
        observation = await session.aobserve()
        labels = {action.text_label: action.id for action in observation.space.interaction_actions}

        for label in ("Choose a photo", "Browse files"):
            result = await session.aexecute(type="click", id=labels[label], raise_on_failure=False)
            assert not result.success, label
            assert isinstance(result.exception, FileChooserOpenedError)
            assert result.message is not None and "opened a file chooser" in result.message

        # a click the page cancels opens no chooser; other clicks are not affected
        for label in ("Locked", "Save"):
            result = await session.aexecute(type="click", id=labels[label], raise_on_failure=False)
            assert result.success, result.message
        assert await session.window.page.inner_text("button >> nth=-1") == "Saved"


@pytest.mark.asyncio
async def test_a_cancelled_click_removes_its_file_chooser_listener() -> None:
    window = MagicMock()
    started = asyncio.Event()

    async def hang(_script: str) -> None:
        started.set()
        await asyncio.Event().wait()

    window.page.evaluate_handle = AsyncMock(side_effect=hang)
    task = asyncio.ensure_future(execute(window, ClickAction(selector="#pick")))
    await started.wait()
    _ = task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    [(event, listener)] = [call.args for call in window.page.on.call_args_list]
    window.page.remove_listener.assert_called_once_with(event, listener)
