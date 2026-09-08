"""Real Chromium/CDP recovery with local transport faults; no API credentials needed.

Only the REST session metadata/stop calls are stubbed. RemoteSession initialization,
its lazy Playwright driver, WebSocket handshakes and page objects are real.
"""

import asyncio
import subprocess
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from notte_sdk.endpoints.sessions import RemoteSession, SessionsClient
from notte_sdk.types import SessionResponse
from patchright.async_api import async_playwright as browser_playwright
from websockets.asyncio.client import connect
from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed

# Playwright is an optional SDK dependency, installed by the CI all-extras environment.
playwright_async = pytest.importorskip("playwright.async_api")
playwright_sync = pytest.importorskip("playwright.sync_api")
AsyncError = playwright_async.Error
SyncError = playwright_sync.Error


@asynccontextmanager
async def chromium_endpoint(executable: str, profile: Path):
    with subprocess.Popen(
        [
            executable,
            "--headless",
            "--no-sandbox",
            "--remote-debugging-address=127.0.0.1",
            "--remote-debugging-port=0",
            f"--user-data-dir={profile}",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ) as process:
        try:
            port_file = profile / "DevToolsActivePort"
            async with asyncio.timeout(15):
                while True:
                    assert process.poll() is None, "Chromium exited before opening CDP"
                    if port_file.exists():
                        lines = port_file.read_text().splitlines()
                        if len(lines) >= 2:
                            break
                    await asyncio.sleep(0.05)
            yield f"ws://127.0.0.1:{lines[0]}{lines[1]}"
        finally:
            process.terminate()
            try:
                await asyncio.to_thread(process.wait, timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                await asyncio.to_thread(process.wait)


@asynccontextmanager
async def interruptible_proxy(upstream: str, close_code: int):
    clients = set()

    async def proxy(client):
        clients.add(client)
        try:
            async with connect(upstream, max_size=None) as remote:

                async def forward(source, destination):
                    async for message in source:
                        await destination.send(message)

                tasks = [asyncio.create_task(forward(client, remote)), asyncio.create_task(forward(remote, client))]
                try:
                    await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                finally:
                    for task in tasks:
                        task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
        except ConnectionClosed:
            pass  # The injected fault deliberately closes this connection.
        finally:
            clients.discard(client)

    async def drop():
        assert clients, "No CDP connection to interrupt"
        for client in list(clients):
            if close_code == 1001:
                await client.close(code=1001, reason="CloudFlare WebSocket proxy restarting")
            else:
                # 1006 is observed locally for a lost transport, never sent on wire.
                client.transport.abort()

    async with serve(proxy, "127.0.0.1", 0, max_size=None) as server:
        yield f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}", drop


def local_session(endpoint: str) -> RemoteSession:
    client = MagicMock(spec=SessionsClient)
    client.root_client = MagicMock()
    client.status.return_value = SessionResponse(
        session_id="00000000-0000-0000-0000-000000000001",
        created_at=datetime.now(timezone.utc),
        last_accessed_at=datetime.now(timezone.utc),
        idle_timeout_minutes=30,
        status="active",
    )
    return RemoteSession(session_id=client.status.return_value.session_id, cdp_url=endpoint, _client=client)


def sync_recovery(endpoint, drop, loop):
    session = local_session(endpoint)
    try:
        page = session.page
        page.locator("#value").fill("unsaved data")
        before = page.context.new_cdp_session(page).send("Target.getTargetInfo")["targetInfo"]["targetId"]
        asyncio.run_coroutine_threadsafe(drop(), loop).result(timeout=10)
        with pytest.raises(SyncError, match="closed"):
            page.title()

        recovered = session.reconnect(timeout_ms=5_000)
        after = recovered.context.new_cdp_session(recovered).send("Target.getTargetInfo")["targetInfo"]["targetId"]
        assert after == before
        assert recovered is session.page
        assert recovered.locator("#value").input_value() == "unsaved data"
        assert any(
            cookie["name"] == "probe" and cookie["value"] == "preserved" for cookie in recovered.context.cookies()
        )
        with pytest.raises(SyncError, match="closed"):
            page.title()
        session.client.stop.assert_not_called()
        session.client.start.assert_not_called()
    finally:
        session.__exit__(None, None, None)


@pytest.mark.asyncio
@pytest.mark.parametrize("close_code", [1001, 1006])
@pytest.mark.parametrize("api", ["sync", "async"])
async def test_reconnect_preserves_live_browser(tmp_path, close_code, api):
    async with browser_playwright() as installed_browser, playwright_async.async_playwright() as playwright:
        async with chromium_endpoint(installed_browser.chromium.executable_path, tmp_path) as upstream:
            observer = await playwright.chromium.connect_over_cdp(upstream)
            try:
                truth = observer.contexts[0].pages[0]
                await truth.goto('data:text/html,<input id="value">')
                await truth.evaluate("window.committed = 0")
                await truth.context.add_cookies(
                    [{"name": "probe", "value": "preserved", "domain": "example.test", "path": "/"}]
                )
                async with interruptible_proxy(upstream, close_code) as (endpoint, drop):
                    if api == "sync":
                        await asyncio.to_thread(sync_recovery, endpoint, drop, asyncio.get_running_loop())
                        return
                    session = local_session(endpoint)
                    interrupted = None
                    try:
                        page = await session.apage
                        await page.locator("#value").fill("unsaved data")
                        cdp = await page.context.new_cdp_session(page)
                        before = (await cdp.send("Target.getTargetInfo"))["targetInfo"]["targetId"]
                        # Commit a mutation but withhold its response until after disconnection.
                        interrupted = asyncio.create_task(
                            page.evaluate("() => { window.committed++; return new Promise(() => {}); }")
                        )
                        await truth.wait_for_function("window.committed === 1", timeout=5_000)
                        await drop()
                        with pytest.raises(AsyncError, match="closed"):
                            await asyncio.wait_for(interrupted, timeout=5)

                        recovered = await session.areconnect(timeout_ms=5_000)
                        cdp = await recovered.context.new_cdp_session(recovered)
                        after = (await cdp.send("Target.getTargetInfo"))["targetInfo"]["targetId"]
                        assert after == before
                        assert recovered is await session.apage
                        assert await recovered.locator("#value").input_value() == "unsaved data"
                        assert await recovered.evaluate("window.committed") == 1
                        assert any(
                            cookie["name"] == "probe" and cookie["value"] == "preserved"
                            for cookie in await recovered.context.cookies()
                        )
                        with pytest.raises(AsyncError, match="closed"):
                            await page.title()
                        session.client.stop.assert_not_called()
                        session.client.start.assert_not_called()
                    finally:
                        if interrupted is not None:
                            interrupted.cancel()
                            await asyncio.gather(interrupted, return_exceptions=True)
                        await session.__aexit__(None, None, None)
            finally:
                await observer.close()
