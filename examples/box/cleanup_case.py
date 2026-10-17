"""Inject a native disconnect failure after closing a real owned connection."""

import asyncio
import json
import os
import sys
import threading
from pathlib import Path
from unittest.mock import patch

import main as demo
from notte_sdk import NotteClient
from playwright.async_api import BrowserType as AsyncBrowserType
from playwright.sync_api import BrowserType

mode = sys.argv[1]
client, ids, closes, navigations = NotteClient(), [], [], []
start = client.sessions.start
sync_connect = BrowserType.connect_over_cdp
async_connect = AsyncBrowserType.connect_over_cdp


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
        close()
        closes.append(True)
        if mode == "close-timeout":
            threading.Event().wait()
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
        await close()
        closes.append(True)
        if mode == "close-timeout":
            await asyncio.Future()
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
    assert client.sessions.status(ids[0]).status == "closed", "Owner did not release its browser"
    print(json.dumps({"session_id": ids[0], "closed": True, "mode": mode}))
finally:
    for session_id in ids:
        if client.sessions.status(session_id).status != "closed":
            client.sessions.stop(session_id)
            assert client.sessions.status(session_id).status == "closed"
