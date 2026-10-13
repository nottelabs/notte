import asyncio
import socket
from contextlib import closing
from unittest.mock import AsyncMock, patch

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


@pytest.mark.asyncio
@pytest.mark.parametrize("wait_until", ["commit", "domcontentloaded", "load", "networkidle", None])
async def test_requested_load_event_with_stalled_image(wait_until: str | None) -> None:
    release_image = asyncio.Event()

    async def document(_request: web.Request) -> web.Response:
        return web.Response(text='<html><body><img src="/image"></body></html>', content_type="text/html")

    async def image(_request: web.Request) -> web.Response:
        await release_image.wait()
        return web.Response(body=b"", content_type="image/png")

    app = web.Application()
    app.router.add_get("/", document)
    app.router.add_get("/image", image)
    runner = web.AppRunner(app)
    await runner.setup()
    with closing(socket.socket()) as server_socket:
        server_socket.bind(("127.0.0.1", 0))
        server_socket.listen()
        port = server_socket.getsockname()[1]
        try:
            await web.SockSite(runner, server_socket).start()
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(channel="chromium", headless=True)
                page = await browser.new_page()
                resource = BrowserResource.model_construct(page=page, options=None)
                window = BrowserWindow(resource=resource)
                test_config = config.model_copy(update={"timeout_goto_ms": 1000})
                try:
                    with (
                        patch.object(window_module, "config", test_config),
                        patch.object(BrowserWindow, "long_wait", new_callable=AsyncMock) as long_wait,
                        patch.object(BrowserWindow, "short_wait", new_callable=AsyncMock),
                    ):
                        await window.goto_and_wait(f"http://127.0.0.1:{port}/", wait_until=wait_until)  # type: ignore[arg-type]
                    assert window.goto_response is not None
                    assert window.goto_response.status == 200
                    long_wait.assert_not_awaited()
                finally:
                    release_image.set()
                    await window.close()
                    await browser.close()
        finally:
            release_image.set()
            await runner.cleanup()
