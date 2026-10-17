"""Keep native authentication errors private when browser disconnect fails."""

import asyncio
import json
import sys
from unittest.mock import patch

import demo
from notte_sdk import NotteClient
from playwright.async_api import BrowserType


async def check(mode):
    client, ids, closes = NotteClient(), [], []
    start = client.sessions.start
    connect = BrowserType.connect_over_cdp

    def started(**kwargs):
        response = start(**kwargs)
        ids.append(response.session_id)
        return response

    async def connected(browser_type, *args, **kwargs):
        browser = await connect(browser_type, *args, **kwargs)
        close = browser.close

        async def disconnect():
            await close()
            closes.append(True)
            if mode == "timeout":
                await asyncio.Future()
            raise RuntimeError("PRIVATE_CLOSE_CREDENTIAL")

        browser.close = disconnect
        return browser

    failure = None
    try:
        with (
            patch.object(demo, "NotteClient", return_value=client),
            patch.object(client.sessions, "start", side_effect=started),
            patch.object(BrowserType, "connect_over_cdp", new=connected),
        ):
            try:
                async with asyncio.timeout(20):
                    await demo.run_demo()
            except Exception as error:
                failure = str(error)
        assert len(ids) == len(closes) == 1
        closed = client.sessions.status(ids[0]).status == "closed"
        print(json.dumps({"session_id": ids[0], "closed_before_compensation": closed}), flush=True)
        assert closed, "The recipe did not stop its browser"
        assert failure and failure.startswith("Vault form failed: resolve and fill login")
        assert "PRIVATE_" not in failure
        print(json.dumps({"session_id": ids[0], "mode": mode, "closed": True}), flush=True)
    finally:
        for session_id in ids:
            if client.sessions.status(session_id).status != "closed":
                client.sessions.stop(session_id)
                assert client.sessions.status(session_id).status == "closed"


if __name__ == "__main__":
    asyncio.run(check(sys.argv[1]))
