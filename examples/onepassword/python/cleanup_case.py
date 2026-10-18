"""Keep native authentication errors private when browser disconnect fails."""

import asyncio
import json
import os
import sys
from unittest.mock import patch

import demo
import requests
from notte_sdk import NotteClient
from playwright.async_api import BrowserType


async def status(session_id):
    api = (os.environ.get("NOTTE_API_URL") or "https://api.notte.cc").rstrip("/")
    response = await asyncio.to_thread(
        requests.get,
        f"{api}/sessions/{session_id}",
        headers={"Authorization": f"Bearer {os.environ['NOTTE_API_KEY']}"},
        timeout=15,
    )
    assert response.status_code == 200, "Authoritative session lookup failed"
    value = response.json()["status"]
    assert value in {"active", "closed"}, "Unknown session status"
    return value


async def wait_closed(session_id):
    async with asyncio.timeout(15):
        while await status(session_id) != "closed":
            await asyncio.sleep(0.25)
    return True


async def check(mode):
    client, ids, closes = NotteClient(), [], []
    start = client.sessions.start
    connect = BrowserType.connect_over_cdp

    def started(**kwargs):
        response = start(**kwargs)
        ids.append(response.session_id)
        print(json.dumps({"session_id": response.session_id, "claimed": True}), flush=True)
        return response

    async def connected(browser_type, *args, **kwargs):
        browser = await connect(browser_type, *args, **kwargs)
        close = browser.close

        async def disconnect():
            closes.append(True)
            if mode == "timeout":
                await asyncio.Future()
            await close()
            raise RuntimeError("PRIVATE_CLOSE_CREDENTIAL")

        browser.close = disconnect
        return browser

    failure, body_failed = None, False
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
        closed = await wait_closed(ids[0])
        print(json.dumps({"session_id": ids[0], "closed_before_compensation": closed}), flush=True)
        assert closed, "The recipe did not stop its browser"
        assert failure and failure.startswith("Vault form failed: resolve and fill login")
        assert "PRIVATE_" not in failure
        print(json.dumps({"session_id": ids[0], "mode": mode, "closed": True}), flush=True)
    except BaseException:
        body_failed = True
        raise
    finally:
        try:
            for session_id in ids:
                closed = False
                try:
                    closed = await status(session_id) == "closed"
                except Exception:
                    pass  # Closure is unconfirmed; still attempt the owned stop.
                if not closed:
                    client.sessions.stop(session_id)
                await wait_closed(session_id)
        except BaseException:
            if not body_failed:
                raise


if __name__ == "__main__":
    asyncio.run(check(sys.argv[1]))
