import json
import threading
import unittest
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from main import DISABLED
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
