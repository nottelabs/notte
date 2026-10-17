import asyncio
import json
import os
import re
import socket
import threading
import time
import unittest
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

import httpx2
from demo import PipedreamConfig, discover, load_action, run_demo
from notte_sdk import NotteClient

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
                cursor = body.get("params", {}).get("cursor")
                paginated = mode in {"pagination", "cursor_cycle"}
                result = {
                    "tools": [
                        {
                            "name": "fixture_first_page" if paginated and not cursor else "fixture_catalog_read",
                            "description": "Synthetic test tool, not a vendor action",
                            "inputSchema": {"type": "object", "properties": {}},
                            "annotations": {"readOnlyHint": True},
                        }
                    ]
                }
                if paginated and (not cursor or mode == "cursor_cycle"):
                    result["nextCursor"] = "fixture-next"
            elif method == "tools/call":
                result = {
                    "content": [{"type": "text", "text": "private fixture-output detail"}],
                    "isError": mode == "action_error",
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
    api = (os.environ.get("NOTTE_API_URL") or "https://api.notte.cc").rstrip("/")
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
    def test_notte_mcp_uses_api_root_without_network(self):
        original_client = httpx2.AsyncClient
        for value, expected in (
            (None, "https://api.notte.cc/mcp"),
            ("", "https://api.notte.cc/mcp"),
            ("https://example.invalid", "https://example.invalid/mcp"),
            ("https://example.invalid/", "https://example.invalid/mcp"),
            ("https://example.invalid/notte/", "https://example.invalid/notte/mcp"),
        ):
            with self.subTest(api_url=value):
                requests = []

                def reply(request):
                    requests.append(request)
                    return httpx2.Response(401)

                with (
                    patch.dict(
                        os.environ,
                        {"NOTTE_API_KEY": "fixture-config-only"},  # pragma: allowlist secret
                        clear=True,
                    ),
                    patch.object(
                        httpx2,
                        "AsyncClient",
                        side_effect=lambda **kwargs: original_client(transport=httpx2.MockTransport(reply), **kwargs),
                    ),
                    patch.object(socket.socket, "connect", side_effect=AssertionError("Unexpected network")) as network,
                    patch.object(
                        socket.socket, "connect_ex", side_effect=AssertionError("Unexpected network")
                    ) as network_ex,
                ):
                    if value is not None:
                        os.environ["NOTTE_API_URL"] = value
                    with self.assertRaises(Exception):
                        asyncio.run(
                            discover(
                                CONFIG,
                                "fixture-session",
                                "https://oauth.invalid",
                                "https://mcp.invalid",
                                "https://example.com",
                                None,
                            )
                        )
                    self.assertTrue(requests, "The native MCP client must send its initialization")
                    self.assertEqual({str(request.url) for request in requests}, {expected})
                    self.assertTrue(
                        any(
                            request.method == "POST" and json.loads(request.content)["method"] == "initialize"
                            for request in requests
                        )
                    )
                    self.assertTrue(
                        all(request.headers["Authorization"] == "Bearer fixture-config-only" for request in requests)
                    )
                    network.assert_not_called()
                    network_ex.assert_not_called()

    def test_invalid_action_file_is_sanitized(self):
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w+") as file:
            file.write('{"name":"fixture-private-argument","arguments":[]}')
            file.flush()
            with self.assertRaisesRegex(ValueError, "Action file must contain") as error:
                load_action(file.name)
            self.assertNotIn("fixture-private-argument", str(error.exception))
            file.seek(0)
            file.truncate()
            file.write('{"name":"fixture_catalog_read","arguments":{}}')
            file.flush()
            self.assertEqual(load_action(file.name), {"name": "fixture_catalog_read", "arguments": {}})
        self.assertIsNone(load_action(None))

    def test_cancellation_during_claim_reaps_owned_browser(self):
        client = NotteClient()
        original_start = client.sessions.start
        owned = []
        claimed, release = threading.Event(), threading.Event()

        def start(*args, **kwargs):
            response = original_start(*args, **kwargs)
            owned.append(response.session_id)
            claimed.set()
            if not release.wait(15):
                raise TimeoutError("Claim fixture was not released")
            return response

        async def execute():
            with patch.object(client.sessions, "start", start):
                task = asyncio.create_task(run_demo(CONFIG, client=client))
                async with asyncio.timeout(70):
                    while not claimed.is_set() and not task.done():
                        await asyncio.sleep(0.05)
                self.assertTrue(claimed.is_set(), "Native asynchronous claim did not complete")
                task.cancel()
                release.set()
                with self.assertRaises(asyncio.CancelledError) as error:
                    await task
                self.assertIn(owned[0], str(error.exception))

        try:
            with asyncio.Runner() as runner:
                runner.run(execute())
        finally:
            release.set()
        row = closed(owned[0])
        self.assertFalse(any(step.get("type") == "execution_result" for step in row["steps"]))
        print(f"claim cancellation: owned browser {owned[0]} independently closed")

    def test_native_transports_and_owned_browser_cleanup(self):
        self.check_modes(
            ["success", "action", "action_error", "unoffered", "oauth401", "mcp401", "navigation", "cancel"]
        )

    def test_native_pagination_and_cursor_refusal(self):
        self.check_modes(["pagination", "cursor_cycle"])

    def check_modes(self, modes):
        for mode in modes:
            with self.subTest(mode=mode), provider(mode) as (base, state):

                async def execute():
                    task = asyncio.create_task(
                        run_demo(
                            CONFIG,
                            approved_action={
                                "name": "fixture_not_offered" if mode == "unoffered" else "fixture_catalog_read",
                                "arguments": {"private": "fixture-private-argument"},
                            }
                            if mode in {"action", "action_error", "unoffered", "pagination", "cursor_cycle"}
                            else None,
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
                    if mode in {"success", "action", "pagination"}:
                        result = runner.run(execute())
                        session_id = result["session_id"]
                        self.assertIn("Example Domain", json.dumps(result["page"]))
                        self.assertEqual(
                            result["tool_names"],
                            ["fixture_first_page", "fixture_catalog_read"]
                            if mode == "pagination"
                            else ["fixture_catalog_read"],
                        )
                        self.assertEqual(result["tool_call_completed"], mode in {"action", "pagination"})
                        self.assertNotIn("fixture-output", json.dumps(result))
                        self.assertNotIn("fixture-private-argument", json.dumps(result))
                    else:
                        error_type = asyncio.CancelledError if mode == "cancel" else RuntimeError
                        with self.assertRaises(error_type) as error:
                            runner.run(execute())
                        message = str(error.exception)
                        self.assertNotIn("fixture-secret", message)
                        self.assertNotIn("fixture-access-token", message)
                        self.assertNotIn("fixture-private-argument", message)
                        self.assertNotIn("fixture-output", message)
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
                calls = [body for _, _, body in requests if body.get("method") == "tools/call"]
                self.assertEqual(len(calls), 1 if mode in {"action", "action_error", "pagination"} else 0)
                if mode in {"pagination", "cursor_cycle"}:
                    lists = [body for _, _, body in requests if body.get("method") == "tools/list"]
                    self.assertEqual(len(lists), 2)
                    self.assertEqual(lists[1]["params"]["cursor"], "fixture-next")
                if calls:
                    self.assertEqual(
                        calls[0]["params"],
                        {"name": "fixture_catalog_read", "arguments": {"private": "fixture-private-argument"}},
                    )
                print(f"{mode}: owned browser {session_id} independently closed")


if __name__ == "__main__":
    unittest.main()
