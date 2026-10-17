"""Isolated native Braintrust logger regression with a real owned browser."""

import asyncio
import json
import os
import sys
from unittest.mock import patch

import demo
from braintrust import set_http_adapter
from braintrust.logger import (
    Logger,
    ObjectMetadata,
    OrgProjectMetadata,
    _internal_with_memory_background_logger,
)
from braintrust.util import LazyValue
from notte_sdk import NotteClient
from playwright.async_api import BrowserType
from requests.adapters import HTTPAdapter


class RejectVendorHTTP(HTTPAdapter):
    def send(self, *args, **kwargs):
        raise AssertionError("Unexpected vendor HTTP request")


async def check(mode):
    set_http_adapter(RejectVendorHTTP())
    client, ids, closes, flushes = NotteClient(), [], [], []
    start = client.sessions.start
    connect = BrowserType.connect_over_cdp

    def started(**kwargs):
        response = start(**kwargs)
        ids.append(response.session_id)
        return response

    async def connected(browser_type, *args, **kwargs):
        browser = await connect(browser_type, *args, **kwargs)
        original_close = browser.close

        async def close():
            await original_close()
            closes.append(True)
            if mode == "navigation":
                raise RuntimeError("PRIVATE_CLEANUP_BODY https://private.invalid/credential")
            if mode == "close-timeout":
                await asyncio.Future()

        browser.close = close
        return browser

    with _internal_with_memory_background_logger() as memory:
        logger = Logger(
            LazyValue(
                lambda: OrgProjectMetadata(
                    org_id="00000000-0000-4000-8000-000000000001",
                    project=ObjectMetadata(id="00000000-0000-4000-8000-000000000002", name="offline", full_info={}),
                ),
                use_mutex=True,
            ),
            link_args={"app_url": "https://offline.invalid", "org_name": "offline"},
        )
        original_flush = logger.flush

        def flush():
            original_flush()
            flushes.append(True)
            if mode != "success":
                raise RuntimeError("PRIVATE_FLUSH_BODY https://private.invalid/credential")

        result, failure = None, None
        try:
            with (
                patch.object(demo, "init_logger", return_value=logger),
                patch.object(demo, "NotteClient", return_value=client),
                patch.object(client.sessions, "start", side_effect=started),
                patch.object(BrowserType, "connect_over_cdp", new=connected),
                patch.object(logger, "flush", side_effect=flush),
            ):
                try:
                    result = await demo.run_demo("not-a-valid-url" if mode == "navigation" else "https://example.com")
                except Exception as error:
                    failure = str(error)
            assert len(ids) == len(closes) == len(flushes) == 1
            closed = client.sessions.status(ids[0]).status == "closed"
            print(
                json.dumps(
                    {
                        "mode": mode,
                        "session_id": ids[0],
                        "closed_before_compensation": closed,
                        "private_body": "PRIVATE_" in (failure or ""),
                        "navigation_error_preserved": bool(
                            failure and failure.startswith("Browser task failed: navigate")
                        ),
                    }
                )
            )
            assert closed, "Owner did not release its browser"
            rows = memory.pop()
            serialized = json.dumps(rows)
            for value in [os.environ["NOTTE_API_KEY"], os.environ["BRAINTRUST_API_KEY"], "PRIVATE_", "wss://"]:
                assert value not in serialized and value not in (failure or ""), "Private data escaped error handling"
            assert any(row.get("metadata", {}).get("session_id") == ids[0] for row in rows)
            if mode == "success":
                assert failure is None and result["title"] == "Example Domain"
                assert any(row.get("output", {}).get("title") == "Example Domain" for row in rows)
            else:
                prefix = (
                    "Browser task failed: navigate"
                    if mode == "navigation"
                    else "Browser task failed: disconnect browser"
                    if mode == "close-timeout"
                    else "Braintrust trace flush failed"
                )
                assert failure and failure.startswith(prefix), "The primary failure was replaced"
                assert ids[0] in failure
            print(json.dumps({"mode": mode, "session_id": ids[0], "closed": True, "native_flush_calls": len(flushes)}))
        finally:
            # Negative-baseline probes must also reap their own browser.
            for session_id in ids:
                if client.sessions.status(session_id).status != "closed":
                    client.sessions.stop(session_id)
                    assert client.sessions.status(session_id).status == "closed"


if __name__ == "__main__":
    asyncio.run(check(sys.argv[1]))
