import asyncio
import json
import os
import sys
from contextlib import nullcontext
from unittest.mock import patch

import demo
import httpx
from demo import run_demo
from fixture import CODE, Wire
from notte_sdk import NotteClient
from playwright.async_api import BrowserType
from tzafon import AsyncLightcone


async def main() -> dict:
    mode = sys.argv[1]
    closing = mode in ("reject-close", "reject-timeout", "caller-except-close")
    wire = Wire("reject" if mode.startswith("reject") else mode, real_screenshot=True)
    client = NotteClient()
    start = client.sessions.start
    connect = BrowserType.connect_over_cdp
    closes = []

    def started(**kwargs):
        response = start(**kwargs)
        event = json.dumps({"event": "owned", "session_id": response.session_id})
        print(event, flush=True)
        if path := os.environ.get("TZAFON_OWNERSHIP_JOURNAL"):
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

    async with httpx.AsyncClient(transport=httpx.MockTransport(wire)) as http:
        provider = AsyncLightcone(
            api_key="fixture-provider-key",  # pragma: allowlist secret
            base_url="https://lightcone.invalid",
            http_client=http,
            max_retries=0,  # pragma: allowlist secret
        )
        try:
            with (
                patch.object(demo, "NotteClient", return_value=client),
                patch.object(client.sessions, "start", side_effect=started),
                patch.object(BrowserType, "connect_over_cdp", new=connected) if closing else nullcontext(),
            ):
                if mode == "caller-except-close":
                    try:
                        raise ValueError("Unrelated caller exception")
                    except ValueError:
                        result = await run_demo(provider, CODE)
                else:
                    result = await run_demo(provider, CODE)
        except Exception:
            assert len(wire.requests) == (3 if mode == "caller-except-close" else 1)
            raise
        finally:
            if closing:
                assert closes == [True], "The native disconnect fault must run"
        assert len(wire.requests) == 3
        return result


try:
    with asyncio.Runner() as runner:
        print(json.dumps(runner.run(main())))
except Exception as error:
    print(str(error))
    raise SystemExit(1) from None
