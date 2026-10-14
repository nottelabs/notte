import json
import os
import socket
import subprocess
import time
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest
from notte_browser.playwright import PlaywrightManager
from notte_browser.playwright_async_api import Error, async_playwright
from notte_browser.window import BrowserWindowOptions
from notte_sdk.types import LocalSessionStartRequest
from patchright.sync_api import sync_playwright


def _browser_version(cdp_url: str) -> dict[str, str]:
    with urllib.request.urlopen(f"{cdp_url}/json/version", timeout=2) as response:
        return json.load(response)


@pytest.fixture
def cdp_browser(tmp_path: Path) -> Iterator[str]:
    """A Chromium started outside Notte, reachable over CDP.

    NOTTE_TEST_CHROMIUM_EXECUTABLE can select an existing local Chrome installation.
    """
    with sync_playwright() as p:
        executable = os.environ.get("NOTTE_TEST_CHROMIUM_EXECUTABLE") or p.chromium.executable_path
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    process = subprocess.Popen(
        [
            executable,
            "--headless=new",
            f"--remote-debugging-port={port}",
            f"--user-data-dir={tmp_path / 'profile'}",
            "--no-first-run",
            "--no-default-browser-check",
            # Same flags Playwright uses for the browsers it launches, so this also runs in containers.
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    cdp_url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 30
        while True:
            try:
                _ = _browser_version(cdp_url)
                break
            except OSError:
                if process.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError("External Chromium did not expose its CDP endpoint")
                time.sleep(0.2)
        yield cdp_url
    finally:
        process.terminate()
        try:
            _ = process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            _ = process.wait(timeout=10)


@pytest.mark.asyncio
@pytest.mark.parametrize("fail_browser_close", [False, True], ids=["normal-close", "failed-close"])
async def test_new_window_releases_owned_cdp_resources_and_preserves_external_browser(
    cdp_browser: str, monkeypatch: pytest.MonkeyPatch, fail_browser_close: bool
):
    # Keep a separate connection so we can inspect the external browser after Notte disconnects.
    async with async_playwright() as observer:
        browser = await observer.chromium.connect_over_cdp(cdp_browser)
        cdp = await browser.new_browser_cdp_session()
        before = set((await cdp.send("Target.getBrowserContexts"))["browserContextIds"])
        external_context = browser.contexts[0]
        external_page = external_context.pages[0]
        await external_context.add_cookies(
            [{"name": "external-cookie", "value": "external", "domain": "example.invalid", "path": "/"}]
        )
        manager = PlaywrightManager()
        driver = None
        options = BrowserWindowOptions.from_request(LocalSessionStartRequest(headless=True, cdp_url=cdp_browser))

        try:
            window = await manager.new_window(options)
            driver = manager.playwright
            page = window.page
            if fail_browser_close:
                owned_browser = page.context.browser
                assert owned_browser is not None

                async def fail_close() -> None:
                    raise RuntimeError("Synthetic browser close failure")

                monkeypatch.setattr(owned_browser, "close", fail_close)
            try:
                during = set((await cdp.send("Target.getBrowserContexts"))["browserContextIds"])
                assert before < during
                assert len(during - before) == 1
                assert await page.context.cookies() == []
                await page.context.add_cookies(
                    [{"name": "owned-cookie", "value": "owned", "domain": "example.invalid", "path": "/"}]
                )
                await page.goto("data:text/html,<title>notte-cdp</title>")
                assert await page.title() == "notte-cdp"
            finally:
                await window.close()

            assert page.is_closed()
            assert not manager.is_started()
            assert set((await cdp.send("Target.getBrowserContexts"))["browserContextIds"]) == before
            assert {cookie["name"] for cookie in await external_context.cookies()} == {"external-cookie"}
            assert not external_page.is_closed()
            assert "Browser" in _browser_version(cdp_browser)
            # The endpoint is still healthy, but the stopped driver can no longer connect to it.
            with pytest.raises(Error):
                await driver.chromium.connect_over_cdp(cdp_browser, timeout=1_000)
        finally:
            await manager.astop()
            if driver is not None:
                await driver.stop()
            await browser.close()
