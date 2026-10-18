"""Isolated native Braintrust logger regression with a real owned browser."""

import asyncio
import json
import os
import sys
import uuid
from unittest.mock import patch

import demo
import requests
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


async def wait_closed(session_id, observation):
    async with asyncio.timeout(15):
        while True:
            observation["closed"] = await status(session_id) == "closed"
            if observation["closed"]:
                return True
            await asyncio.sleep(0.25)


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
        body_failed, closures = False, []
        observation = {"closed": None}
        phase = "run demo"
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
            phase = "independent owner status"
            closed = await wait_closed(ids[0], observation)
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
            phase = "trace privacy"
            rows = memory.pop()
            serialized = json.dumps(rows)
            for value in [os.environ["NOTTE_API_KEY"], os.environ["BRAINTRUST_API_KEY"], "PRIVATE_", "wss://"]:
                assert value not in serialized and value not in (failure or ""), "Private data escaped error handling"
            phase = "trace metadata"
            assert any(row.get("metadata", {}).get("session_id") == ids[0] for row in rows)
            phase = "primary result"
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
            phase = "passed"
            print(json.dumps({"mode": mode, "session_id": ids[0], "closed": True, "native_flush_calls": len(flushes)}))
        except BaseException:
            body_failed = True
            raise
        finally:
            # Negative-baseline probes must also reap their own browser.
            try:
                for session_id in ids:
                    assert str(uuid.UUID(session_id)) == session_id
                    closure = {"session_id": session_id, "closed": None}
                    closures.append(closure)
                    closed = False
                    try:
                        closed = await status(session_id) == "closed"
                    except Exception:
                        pass  # Closure is unconfirmed; still attempt the owned stop.
                    if not closed:
                        client.sessions.stop(session_id)
                    closure["closed"] = await status(session_id) == "closed"
                    assert closure["closed"], "Owned browser remained active"
            except BaseException:
                if not body_failed:
                    raise
            finally:
                print(
                    json.dumps(
                        {
                            "native_cleanup_receipt": True,
                            "mode": mode,
                            "phase": phase,
                            "failure_category": "none" if failure is None else "other",
                            "closed_before_compensation": observation["closed"],
                            "closures": closures,
                        }
                    )
                )


if __name__ == "__main__":
    asyncio.run(check(sys.argv[1]))
