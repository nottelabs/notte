import asyncio
import json
import threading
import time
import unittest
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from unittest.mock import patch

import main as demo
from main import DISABLED
from notte_sdk import NotteClient
from yutori import AsyncYutoriClient
from yutori.navigator import N1_5_MODEL, TOOL_SET_CORE


def completion(name=None, arguments=None):
    message = {"role": "assistant", "content": None if name else "Example Domain"}
    if name:
        message["tool_calls"] = [
            {"id": "step-1", "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}
        ]
    return {
        "id": "fixture-response",
        "object": "chat.completion",
        "created": 1,
        "model": N1_5_MODEL,
        "choices": [{"index": 0, "message": message, "finish_reason": "tool_calls" if name else "stop"}],
    }


@contextmanager
def model_endpoint(responses, status=200):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append({"path": self.path, "payload": payload})
            response = responses[min(len(requests) - 1, len(responses) - 1)]
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(response).encode())

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1", requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


class NativeProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_caller_exception_does_not_change_owned_cleanup(self):
        for cleanup_fails in (False, True):
            with self.subTest(cleanup_fails=cleanup_fails):
                session = NotteClient(api_key="test-only").Session(wait_for_authentication=False)
                with (
                    patch.object(demo, "NotteClient", return_value=SimpleNamespace(Session=lambda **_kwargs: session)),
                    patch.object(session, "start"),
                    patch.object(session, "cdp_url", return_value="wss://test-only.invalid"),
                    patch.object(
                        session, "stop", side_effect=RuntimeError("PRIVATE_CLEANUP_FIXTURE") if cleanup_fails else None
                    ) as stop,
                ):
                    try:
                        raise ValueError("PRIVATE_CALLER_FIXTURE")
                    except ValueError:
                        if cleanup_fails:
                            with self.assertRaisesRegex(demo.BrowserTaskError, "Yutori browser cleanup failed"):
                                async with demo.owned_connection():
                                    pass
                        else:
                            async with demo.owned_connection():
                                pass
                    stop.assert_called_once_with(close_reason="manual")

    async def test_owner_cleanup_failure_is_safe_and_preserves_primary_error(self):
        for primary in (None, demo.BrowserTaskError("Yutori primary task failed")):
            with self.subTest(primary=primary is not None):
                session = NotteClient(api_key="test-only").Session(wait_for_authentication=False)
                with (
                    patch.object(demo, "NotteClient", return_value=SimpleNamespace(Session=lambda **_kwargs: session)),
                    patch.object(session, "start"),
                    patch.object(session, "cdp_url", return_value="wss://test-only.invalid"),
                    patch.object(session, "stop", side_effect=RuntimeError("PRIVATE_CLEANUP_FIXTURE")) as stop,
                ):
                    with self.assertRaises(demo.BrowserTaskError) as caught:
                        async with demo.owned_connection():
                            if primary is not None:
                                raise primary
                    if primary is not None:
                        self.assertIs(caught.exception, primary)
                        self.assertEqual(primary.__notes__, ["Yutori browser cleanup failed"])
                    else:
                        self.assertEqual(str(caught.exception), "Yutori browser cleanup failed")
                        self.assertIsNone(caught.exception.__cause__)
                        self.assertTrue(caught.exception.__suppress_context__)
                    stop.assert_called_once_with(close_reason="error" if primary is not None else "manual")

    async def test_connection_failure_is_safe_and_stops_owned_session(self):
        session = NotteClient(api_key="test-only").Session(wait_for_authentication=False)
        with (
            patch.object(demo, "NotteClient", return_value=SimpleNamespace(Session=lambda **_kwargs: session)),
            patch.object(session, "start"),
            patch.object(session, "cdp_url", side_effect=RuntimeError("PRIVATE_CONNECTION_FIXTURE")),
            patch.object(session, "stop") as stop,
        ):
            with self.assertRaisesRegex(demo.BrowserTaskError, "Yutori browser connection failed") as caught:
                async with demo.owned_connection():
                    self.fail("A failed connection must not enter the browser task")
            self.assertTrue(caught.exception.__suppress_context__)
            self.assertIsNone(caught.exception.__cause__)
            stop.assert_called_once_with(close_reason="error")

    async def test_repeated_startup_cancellation_joins_owned_creation_and_stops(self):
        session = NotteClient(api_key="test-only").Session(wait_for_authentication=False)
        started, release = threading.Event(), threading.Event()
        calls = []

        def start(*_args, **_kwargs):
            started.set()
            assert release.wait(5), "Release the bounded startup fixture"
            calls.append("created")

        async def connect():
            async with demo.owned_connection():
                self.fail("Cancelled startup must not enter the browser task")

        with (
            patch.object(demo, "NotteClient", return_value=SimpleNamespace(Session=lambda **_kwargs: session)),
            patch.object(session, "start", side_effect=start),
            patch.object(session, "stop", side_effect=lambda **_kwargs: calls.append("stopped")) as stop,
        ):
            task = asyncio.create_task(connect())
            try:
                self.assertTrue(await asyncio.to_thread(started.wait, 2))
                task.cancel()
                await asyncio.sleep(0)
                task.cancel()
            finally:
                release.set()
                with self.assertRaises(asyncio.CancelledError):
                    await task
                await asyncio.to_thread(lambda: None)
            stop.assert_called_once_with(close_reason="error")
        self.assertEqual(calls, ["created", "stopped"])

    async def test_sdk_lifecycle_and_connection_lookup_leave_loop_responsive(self):
        session = NotteClient(api_key="test-only").Session(wait_for_authentication=False)
        calls = []
        ticks = []
        loop_thread = threading.get_ident()

        def blocking(name, result=None):
            def operation(*_args, **_kwargs):
                calls.append((name, threading.get_ident()))
                time.sleep(0.1)
                return result

            return operation

        async def heartbeat():
            while True:
                ticks.append(True)
                await asyncio.sleep(0.01)

        with (
            patch.object(demo, "NotteClient", return_value=SimpleNamespace(Session=lambda **_kwargs: session)),
            patch.object(session, "start", side_effect=blocking("start")),
            patch.object(session, "cdp_url", side_effect=blocking("connection", "wss://test-only.invalid")),
            patch.object(session, "stop", side_effect=blocking("stop")) as stop,
        ):
            pulse = asyncio.create_task(heartbeat())
            try:
                async with demo.owned_connection() as (owned, endpoint):
                    self.assertIs(owned, session)
                    self.assertEqual(endpoint, "wss://test-only.invalid")
            finally:
                pulse.cancel()
                await asyncio.gather(pulse, return_exceptions=True)
            stop.assert_called_once_with(close_reason="manual")
        self.assertEqual([name for name, _ in calls], ["start", "connection", "stop"])
        self.assertTrue(all(thread != loop_thread for _, thread in calls))
        self.assertGreater(len(ticks), 3)

    async def test_unmodified_sdk_serializes_native_model_contract(self):
        with model_endpoint([completion("goto_url", {"url": "https://example.com"})]) as (url, requests):
            async with AsyncYutoriClient(api_key="test-only", base_url=url) as client:  # pragma: allowlist secret
                result = await client.chat.completions.create(
                    model=N1_5_MODEL,
                    messages=[{"role": "user", "content": "Read this page"}],
                    tool_set=TOOL_SET_CORE,
                    disable_tools=DISABLED,
                )
            self.assertEqual(result.choices[0].message.tool_calls[0].function.name, "goto_url")
            self.assertEqual(requests[0]["path"], "/v1/chat/completions")
            self.assertEqual(requests[0]["payload"]["model"], N1_5_MODEL)
            self.assertEqual(requests[0]["payload"]["tool_set"], TOOL_SET_CORE)
            self.assertEqual(requests[0]["payload"]["disable_tools"], DISABLED)


if __name__ == "__main__":
    unittest.main()
