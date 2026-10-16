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
            patch.object(session, "stop", side_effect=blocking("stop")),
        ):
            pulse = asyncio.create_task(heartbeat())
            try:
                async with demo.owned_connection() as (owned, endpoint):
                    self.assertIs(owned, session)
                    self.assertEqual(endpoint, "wss://test-only.invalid")
            finally:
                pulse.cancel()
                await asyncio.gather(pulse, return_exceptions=True)
        self.assertEqual([name for name, _ in calls], ["start", "connection", "stop"])
        self.assertTrue(all(thread != loop_thread for _, thread in calls))
        self.assertGreater(len(ticks), 3)

    async def test_unmodified_sdk_serializes_native_model_contract(self):
        with model_endpoint([completion("goto_url", {"url": "https://example.com"})]) as (url, requests):
            async with AsyncYutoriClient(api_key="test-only", base_url=url) as client:
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
