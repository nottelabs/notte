import asyncio
import socket
from contextlib import closing
from unittest.mock import patch

import notte_browser.window as window_module
import pytest
from aiohttp import web
from notte_browser.errors import PageLoadingError
from notte_browser.playwright_async_api import Error as PlaywrightError
from notte_browser.playwright_async_api import async_playwright
from notte_browser.window import BrowserResource, BrowserWindow
from notte_core.common.config import config


@pytest.mark.asyncio
async def test_redirect_response_does_not_hide_stalled_main_document() -> None:
    release_stalled_request = asyncio.Event()

    async def redirect(_request: web.Request) -> web.StreamResponse:
        raise web.HTTPFound("/stall")

    async def stall(_request: web.Request) -> web.StreamResponse:
        await release_stalled_request.wait()
        return web.Response(text="loaded")

    app = web.Application()
    app.router.add_get("/redirect", redirect)
    app.router.add_get("/stall", stall)
    runner = web.AppRunner(app)
    await runner.setup()

    with closing(socket.socket()) as server_socket:
        server_socket.bind(("127.0.0.1", 0))
        server_socket.listen()
        port = server_socket.getsockname()[1]
        site = web.SockSite(runner, server_socket)
        await site.start()

        try:
            async with async_playwright() as playwright:
                try:
                    browser = await playwright.chromium.launch(headless=True)
                except PlaywrightError as exc:
                    if "Executable doesn't exist" not in str(exc):
                        raise
                    browser = await playwright.chromium.launch(channel="chromium", headless=True)
                page = await browser.new_page()
                resource = BrowserResource.model_construct(page=page, options=None)
                window = BrowserWindow(resource=resource)
                test_config = config.model_copy(update={"timeout_goto_ms": 250})

                try:
                    with (
                        patch.object(window_module, "config", test_config),
                        pytest.raises(PageLoadingError),
                    ):
                        await window.goto_and_wait(f"http://127.0.0.1:{port}/redirect")

                    assert window.goto_response is None
                finally:
                    release_stalled_request.set()
                    await window.close()
                    await browser.close()
        finally:
            release_stalled_request.set()
            await runner.cleanup()
