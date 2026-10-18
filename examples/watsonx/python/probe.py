import asyncio
import base64
import json
import os
import sys
from contextlib import nullcontext
from unittest.mock import patch

import demo
from demo import run_demo
from notte_sdk import NotteClient
from playwright.async_api import BrowserType
from test_demo import Transport


class ScreenshotTransport(Transport):
    def post(self, url, **kwargs):
        if len(self.calls) == 1:
            image = kwargs["json"]["messages"][0]["content"][1]["image_url"]["url"]
            png = base64.b64decode(image.split(",")[1])
            assert png.startswith(b"\x89PNG\r\n\x1a\n") and len(png) > 1000
        return super().post(url, **kwargs)


async def main():
    mode = sys.argv[1]
    closing = mode in ("iam-reject-close", "iam-reject-timeout", "caller-except-close")
    closes = []
    connect = BrowserType.connect_over_cdp
    client = NotteClient()
    start = client.sessions.start

    def started(**kwargs):
        response = start(**kwargs)
        event = json.dumps({"event": "owned", "session_id": response.session_id})
        print(event, flush=True)
        if path := os.environ.get("WATSONX_OWNERSHIP_JOURNAL"):
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
            if mode == "iam-reject-timeout":
                await asyncio.Future()
            raise RuntimeError("PRIVATE_CLOSE_FIXTURE")

        browser.close = disconnect
        return browser

    try:
        with (
            patch.object(BrowserType, "connect_over_cdp", new=connected) if closing else nullcontext(),
            patch.object(demo, "NotteClient", return_value=client),
            patch.object(client.sessions, "start", side_effect=started),
        ):
            return await run_demo(ScreenshotTransport("iam-reject" if mode.startswith("iam-reject") else mode))
    finally:
        if closing:
            assert len(closes) == 1, "The disconnect failure was not exercised"


async def probe():
    if sys.argv[1] == "caller-except-close":
        try:
            raise ValueError("PRIVATE_CALLER_FIXTURE")
        except ValueError:
            return await main()
    return await main()


try:
    with asyncio.Runner() as runner:
        print(json.dumps(runner.run(probe())))
except Exception as error:
    print(str(error))
    raise SystemExit(1) from None
