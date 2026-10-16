"""Own a Notte session, local ChromeDriver, and native Vibium client together."""

import asyncio
import os
import signal
import socket
import subprocess
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from bridge import cdp_bridge
from notte_sdk import NotteClient
from vibium.async_api import browser


async def _finish_owned(task):
    cancelled = False
    while True:
        try:
            return await asyncio.shield(task), cancelled
        except asyncio.CancelledError:
            if task.cancelled():
                raise
            cancelled = True


class NativeDriver:
    def __init__(self):
        self.process = None
        self.http = None
        self.native_id = None
        self.starts = []
        self.stopped = set()

    async def __aenter__(self):
        path = os.environ.get("CHROMEDRIVER_PATH", "")
        if not path or not Path(path).is_file():
            raise RuntimeError("Set CHROMEDRIVER_PATH to a matching ChromeDriver binary")
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        try:
            spawn = asyncio.create_task(
                asyncio.create_subprocess_exec(
                    path,
                    f"--port={port}",
                    "--log-level=OFF",
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
            )
            try:
                self.process = await asyncio.shield(spawn)
            except BaseException:
                # Process creation can complete after the caller is cancelled.
                self.process, _ = await _finish_owned(spawn)
                raise
            self.http = httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}", timeout=20)
            async with asyncio.timeout(10):
                while self.process.returncode is None:
                    try:
                        if (await self.http.get("/status")).is_success:
                            return self
                    except httpx.ConnectError:
                        pass
                    await asyncio.sleep(0.1)
            raise RuntimeError("ChromeDriver did not start")
        except BaseException:
            await self.__aexit__(*sys.exc_info())
            raise

    async def attach(self, address):
        response = await self.http.post(
            "/session",
            json={
                "capabilities": {
                    "alwaysMatch": {
                        "browserName": "chrome",
                        "webSocketUrl": True,
                        "goog:chromeOptions": {"debuggerAddress": address, "windowTypes": ["page", "tab", "other"]},
                    }
                }
            },
        )
        value = response.json().get("value", {})
        self.native_id = value.get("sessionId")
        if not response.is_success or not isinstance(self.native_id, str):
            raise RuntimeError("Native BiDi attachment is unavailable for this Notte session")
        url = value["capabilities"]["webSocketUrl"]
        # Only an owned loopback capability reaches the native client's arguments.
        target = urlsplit(url)
        if target.scheme != "ws" or target.hostname != "127.0.0.1":
            raise RuntimeError("ChromeDriver returned a non-local BiDi URL")
        return url

    async def connect(self, url):
        # The SDK's startup owns a native process. Reap late results after cancellation.
        task = asyncio.create_task(browser.start(url=url, headers={"Authorization": ""}))
        self.starts.append(task)
        return await asyncio.shield(task)

    async def disconnect(self, remote):
        # The native SDK bounds a command to 60 seconds before reaping its process.
        # Cancelling stop itself can skip that process cleanup.
        await asyncio.wait_for(asyncio.shield(asyncio.create_task(remote.stop())), 70)
        self.stopped.add(id(remote))

    async def __aexit__(self, *_args):
        _, cancelled = await _finish_owned(asyncio.create_task(self._close(_args[0])))
        if cancelled and _args[0] is None:
            raise asyncio.CancelledError

    async def _close(self, original_error):
        failed = False
        try:
            # Notte has already stopped before local client cleanup. The pinned
            # SDK bounds its two native startup attempts to 60 seconds each.
            for task in self.starts:
                try:
                    remote = await asyncio.wait_for(asyncio.shield(task), 125)
                    if id(remote) not in self.stopped:
                        await self.disconnect(remote)
                except Exception:
                    failed = True
            if self.native_id is not None:
                try:
                    response = await self.http.delete(f"/session/{self.native_id}", timeout=5)
                    failed = failed or not response.is_success
                except Exception:
                    failed = True
        finally:
            if self.http is not None:
                await self.http.aclose()
            if self.process is not None:
                try:
                    os.killpg(self.process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    await asyncio.wait_for(self.process.wait(), 3)
                except TimeoutError:
                    os.killpg(self.process.pid, signal.SIGKILL)
                    await self.process.wait()
        if failed and original_error is None:
            raise RuntimeError("Native client cleanup failed")


@asynccontextmanager
async def notte_vibium(client=None):
    client = client or NotteClient()
    session = client.Session(max_duration_minutes=3, proxies=False, browser_type="chrome")
    try:
        async with NativeDriver() as driver:
            async with session:
                try:
                    async with cdp_bridge(await asyncio.to_thread(session.cdp_url)) as address:
                        url = await driver.attach(address)
                        yield driver, url, session.session_id
                except asyncio.CancelledError:
                    raise asyncio.CancelledError(f"Vibium cancelled (session {session.session_id})") from None
                except Exception:
                    raise RuntimeError(f"Vibium failed (session {session.session_id})") from None
    except asyncio.CancelledError:
        session_id = session.session_id if session.response is not None else "unallocated"
        raise asyncio.CancelledError(f"Vibium cancelled (session {session_id})") from None
    except Exception:
        session_id = session.session_id if session.response is not None else "unallocated"
        raise RuntimeError(f"Vibium failed (session {session_id})") from None
