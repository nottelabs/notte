import json
import socket
import subprocess
import time
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest
from notte_browser.playwright import PlaywrightManager
from notte_browser.window import BrowserWindowOptions
from notte_sdk.types import LocalSessionStartRequest
from patchright.sync_api import sync_playwright


def _browser_version(cdp_url: str) -> dict[str, str]:
    with urllib.request.urlopen(f"{cdp_url}/json/version", timeout=2) as response:
        return json.load(response)


@pytest.fixture
def cdp_browser(tmp_path: Path) -> Iterator[str]:
    """A Chromium started outside Notte, reachable over CDP."""
    with sync_playwright() as p:
        executable = p.chromium.executable_path
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
        _ = process.wait(timeout=10)


@pytest.mark.asyncio
async def test_new_window_attaches_to_external_cdp_browser(cdp_browser: str):
    manager = PlaywrightManager()
    options = BrowserWindowOptions.from_request(LocalSessionStartRequest(headless=True, cdp_url=cdp_browser))

    window = await manager.new_window(options)
    await window.page.goto("data:text/html,<title>notte-cdp</title>")
    assert await window.page.title() == "notte-cdp"

    await window.close()

    assert not manager.is_started()
    # Closing the window disconnects from the browser; the external browser keeps running.
    assert "Browser" in _browser_version(cdp_browser)
