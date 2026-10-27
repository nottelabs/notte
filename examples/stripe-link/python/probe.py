"""Exercise the original demo with the native wallet SDK and an offline HTTP response."""

import asyncio
import json
import os
import sys
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

import demo
import httpx
from demo import run_demo
from link import AsyncClient
from notte_sdk import AsyncNotteClient
from playwright.async_api import BrowserType


async def main() -> dict:
    fixture = json.loads((Path(__file__).parents[1] / "test-card.json").read_text())
    mode = sys.argv[1] if len(sys.argv) > 1 else "fixture"
    reject = mode.startswith("reject")
    closing = mode in ("reject-close", "reject-timeout")
    closes = []
    connect = BrowserType.connect_over_cdp
    client = AsyncNotteClient()
    start = client.sessions.start

    async def started(**kwargs):
        response = await start(**kwargs)
        event = json.dumps({"session_id": response.session_id, "event": "owned"})
        print(event, flush=True)
        if path := os.environ.get("LINK_OWNERSHIP_JOURNAL"):
            try:
                with open(path, "a") as journal:
                    journal.write(event + "\n")
                    journal.flush()
                    os.fsync(journal.fileno())
            except OSError:
                print("Ownership journal unavailable", file=sys.stderr)
        return response

    async def connected(browser_type, *args, **kwargs):
        browser = await connect(browser_type, *args, **kwargs)
        close = browser.close

        async def disconnect():
            await close()
            closes.append(True)
            if mode == "reject-timeout":
                await asyncio.Future()
            raise RuntimeError("PRIVATE_CLOSE_FIXTURE")

        browser.close = disconnect
        return browser

    calls = []

    def handle(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET" and request.url.params.get("include") == "card"
        calls.append(True)
        if reject:
            return httpx.Response(401, json={"error": {"message": "PRIVATE_FIXTURE_BODY"}})
        return httpx.Response(200, json=fixture)

    try:
        with (
            patch.object(BrowserType, "connect_over_cdp", new=connected) if closing else nullcontext(),
            patch.object(demo, "AsyncNotteClient", return_value=client),
            patch.object(client.sessions, "start", side_effect=started),
        ):
            async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as transport:
                result = await run_demo(AsyncClient(access_token="test-link-token", http_client=transport))
    finally:
        if closing:
            assert len(closes) == 1, "The disconnect failure was not exercised"
    assert len(calls) == 1
    return result


if __name__ == "__main__":
    try:
        with asyncio.Runner() as runner:
            print(json.dumps(runner.run(main())))
    except Exception as error:
        print(str(error))
        raise SystemExit(1) from None
