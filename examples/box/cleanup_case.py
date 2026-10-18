"""Inject a native disconnect failure and verify the owner's browser release."""

import asyncio
import json
import os
import sys
import threading
import time
from pathlib import Path
from unittest.mock import patch

import main as demo
import requests
from notte_sdk import NotteClient
from playwright.async_api import BrowserType as AsyncBrowserType
from playwright.sync_api import BrowserType

mode = sys.argv[1]
client, ids, closes, navigations = NotteClient(), [], [], []
start = client.sessions.start
sync_connect = BrowserType.connect_over_cdp
async_connect = AsyncBrowserType.connect_over_cdp


def status(session_id, timeout=15):
    api = (os.environ.get("NOTTE_API_URL") or "https://api.notte.cc").rstrip("/")
    response = requests.get(
        f"{api}/sessions/{session_id}",
        headers={"Authorization": f"Bearer {os.environ['NOTTE_API_KEY']}"},
        timeout=timeout,
    )
    assert response.status_code == 200, "Authoritative session lookup failed"
    value = response.json()["status"]
    assert value in {"active", "closed"}, "Unknown session status"
    return value


def wait_closed(session_id):
    deadline = time.monotonic() + 15
    while True:
        remaining = deadline - time.monotonic()
        assert remaining > 0, "Owner did not release its browser"
        if status(session_id, timeout=min(5, remaining)) == "closed":
            return True
        time.sleep(min(0.25, max(0, deadline - time.monotonic())))


def started(**kwargs):
    response = start(**kwargs)
    ids.append(response.session_id)
    Path(os.environ["NOTTE_BOX_TEST_JOURNAL"]).write_text(response.session_id)
    return response


def connected(browser_type, *args, **kwargs):
    browser = sync_connect(browser_type, *args, **kwargs)
    close = browser.close
    new_page = browser.contexts[0].new_page

    def page_created(*args, **kwargs):
        page = new_page(*args, **kwargs)
        goto = page.goto

        def navigate(url, **kwargs):
            navigations.append(True)
            return goto("not-a-valid-url" if mode == "navigation" else url, **kwargs)

        page.goto = navigate
        return page

    def closed():
        closes.append(True)
        if mode == "close-timeout":
            threading.Event().wait()
        close()
        raise RuntimeError("PRIVATE_BROWSER_CLOSE https://private.invalid/credential")

    browser.contexts[0].new_page = page_created
    browser.close = closed
    return browser


async def async_connected(browser_type, *args, **kwargs):
    browser = await async_connect(browser_type, *args, **kwargs)
    close = browser.close
    new_page = browser.contexts[0].new_page

    async def page_created(*args, **kwargs):
        page = await new_page(*args, **kwargs)
        goto = page.goto

        async def navigate(url, **kwargs):
            navigations.append(True)
            return await goto("not-a-valid-url" if mode == "navigation" else url, **kwargs)

        page.goto = navigate
        return page

    async def closed():
        closes.append(True)
        if mode == "close-timeout":
            await asyncio.Future()
        await close()
        raise RuntimeError("PRIVATE_BROWSER_CLOSE https://private.invalid/credential")

    browser.contexts[0].new_page = page_created
    browser.close = closed
    return browser


try:
    with (
        patch.object(demo, "NotteClient", return_value=client),
        patch.object(client.sessions, "start", side_effect=started),
        patch.object(BrowserType, "connect_over_cdp", new=connected),
        patch.object(AsyncBrowserType, "connect_over_cdp", new=async_connected),
    ):
        failure = None
        try:
            demo.capture_page()
        except Exception as error:
            failure = str(error)
    assert len(ids) == len(closes) == len(navigations) == 1
    assert failure == "Could not capture the hosted page", "Private browser details escaped"
    closed = wait_closed(ids[0])
    print(json.dumps({"session_id": ids[0], "closed": closed, "closed_before_compensation": closed, "mode": mode}))
finally:
    failed = sys.exception() is not None
    try:
        for session_id in ids:
            closed = False
            try:
                closed = status(session_id) == "closed"
            except Exception:
                pass  # Closure is unconfirmed; still attempt the owned stop.
            if not closed:
                client.sessions.stop(session_id)
            wait_closed(session_id)
    except Exception:
        if not failed:
            raise
