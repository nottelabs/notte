import asyncio
import json
import os
import re
import threading
import time
import unittest
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx2
from demo import PipedreamConfig, run_demo

CONFIG = PipedreamConfig("fixture-client", "fixture-secret", "proj_fixture", "user-fixture")


@contextmanager
def provider(mode="success"):
    state = {"requests": [], "waiting": threading.Event(), "release": threading.Event()}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def reply(self, data, status=200):
            body = json.dumps(data).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_GET(self):  # noqa: N802
            self.reply({}, 405)

        def do_DELETE(self):  # noqa: N802
            self.reply({})

        def do_POST(self):  # noqa: N802
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            state["requests"].append((self.path, dict(self.headers), body))
            if self.path == "/v1/oauth/token":
                if mode == "oauth401":
                    return self.reply({"error": "private fixture-secret detail"}, 401)
                return self.reply({"access_token": "fixture-access-token", "token_type": "Bearer", "expires_in": 3600})
            if self.path != "/v3":
                return self.reply({}, 404)
            if mode == "mcp401":
                return self.reply({"error": "private fixture-access-token detail"}, 401)
            method = body["method"]
            if "id" not in body:
                self.send_response(202)
                self.send_header("Content-Length", "0")
                return self.end_headers()
            if method == "initialize":
                result = {
                    "protocolVersion": body["params"]["protocolVersion"],
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "local-pipedream-fixture", "version": "1"},
                }
            elif method == "tools/list":
                if mode == "cancel":
                    state["waiting"].set()
                    state["release"].wait(15)
                result = {
                    "tools": [
                        {
                            "name": "fixture_catalog_read",
                            "description": "Local discovery fixture, not a provider action",
                            "inputSchema": {"type": "object", "properties": {}},
                            "annotations": {"readOnlyHint": True},
                        }
                    ]
                }
            else:
                return self.reply({"error": "Unexpected fixture method"}, 400)
            self.reply({"jsonrpc": "2.0", "id": body["id"], "result": result})

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", state
    finally:
        state["release"].set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def closed(session_id):
    api = os.environ.get("NOTTE_API_URL", "https://api.notte.cc").rstrip("/")
    with httpx2.Client(headers={"Authorization": f"Bearer {os.environ['NOTTE_API_KEY']}"}, timeout=15) as client:
        deadline = time.monotonic() + 15
        while True:
            response = client.get(f"{api}/sessions/{session_id}")
            response.raise_for_status()
            row = response.json()
            if row["status"] == "closed":
                return row
            assert time.monotonic() < deadline, f"Owned browser {session_id} remains active"
            time.sleep(0.5)


class LiveTests(unittest.TestCase):
    def test_native_transports_and_owned_browser_cleanup(self):
        for mode in ["success", "oauth401", "mcp401", "navigation", "cancel"]:
            with self.subTest(mode=mode), provider(mode) as (base, state):

                async def execute():
                    task = asyncio.create_task(
                        run_demo(
                            CONFIG,
                            oauth_url=f"{base}/v1/oauth/token",
                            mcp_url=f"{base}/v3",
                            page_url="https://notte-pipedream-missing.invalid"
                            if mode == "navigation"
                            else "https://example.com",
                        )
                    )
                    if mode == "cancel":
                        async with asyncio.timeout(70):
                            while not state["waiting"].is_set() and not task.done():
                                await asyncio.sleep(0.05)
                        self.assertTrue(
                            state["waiting"].is_set(), "Native MCP discovery did not reach the local fixture"
                        )
                        task.cancel()
                    return await task

                with asyncio.Runner() as runner:
                    if mode == "success":
                        result = runner.run(execute())
                        session_id = result["session_id"]
                        self.assertIn("Example Domain", json.dumps(result["page"]))
                        self.assertEqual(result["tool_names"], ["fixture_catalog_read"])
                    else:
                        error_type = asyncio.CancelledError if mode == "cancel" else RuntimeError
                        with self.assertRaises(error_type) as error:
                            runner.run(execute())
                        message = str(error.exception)
                        self.assertNotIn("fixture-secret", message)
                        self.assertNotIn("fixture-access-token", message)
                        session_id = re.search(r"session ([a-f0-9-]{36})", message).group(1)
                row = closed(session_id)
                if mode != "navigation":
                    self.assertTrue(
                        any(
                            step.get("value", {}).get("action", {}).get("url") == "https://example.com"
                            and step.get("value", {}).get("success") is True
                            for step in row["steps"]
                            if step.get("type") == "execution_result"
                        )
                    )
                requests = state["requests"]
                if mode == "navigation":
                    self.assertEqual(requests, [])
                    print(f"{mode}: owned browser {session_id} independently closed")
                    continue
                self.assertEqual(requests[0][0], "/v1/oauth/token")
                self.assertEqual(
                    requests[0][2],
                    {
                        "grant_type": "client_credentials",
                        "client_id": CONFIG.client_id,
                        "client_secret": CONFIG.client_secret,
                    },
                )
                for path, headers, body in requests[1:]:
                    headers = {key.lower(): value for key, value in headers.items()}
                    self.assertEqual(path, "/v3")
                    self.assertEqual(headers["authorization"], "Bearer fixture-access-token")
                    self.assertEqual(headers["x-pd-project-id"], CONFIG.project_id)
                    self.assertEqual(headers["x-pd-external-user-id"], CONFIG.external_user_id)
                    self.assertEqual(headers["x-pd-environment"], "development")
                    self.assertEqual(headers["x-pd-app-slug"], "github")
                    self.assertNotEqual(body["method"], "tools/call", "Discovery must never invoke vendor actions")
                print(f"{mode}: owned browser {session_id} independently closed")


if __name__ == "__main__":
    unittest.main()
