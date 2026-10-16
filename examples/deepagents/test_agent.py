import asyncio
import json
import os
import threading
import unittest
from contextlib import asynccontextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

import agent
from langchain_core.tools import StructuredTool
from notte_sdk import NotteClient


async def closed(client, session_id):
    for _ in range(30):
        status = await asyncio.to_thread(client.sessions.status, session_id)
        if status.status == "closed":
            return status
        await asyncio.sleep(0.5)
    raise AssertionError("The owned browser session did not close")


@asynccontextmanager
async def owned():
    if not os.getenv("NOTTE_API_URL"):
        raise AssertionError("Choose the browser API explicitly")
    client, ids = NotteClient(), []
    original = client.sessions.start

    def start(**kwargs):
        result = original(**kwargs)
        ids.append(result.session_id)
        return result

    try:
        with (
            patch.object(client.sessions, "start", side_effect=start),
            patch.object(agent, "NotteClient", return_value=client),
        ):
            yield client, ids
    finally:
        for session_id in ids:
            await closed(client, session_id)
        if len(ids) != 1:
            raise AssertionError("The example must own exactly one browser session")


class ToolOwnershipTests(unittest.IsolatedAsyncioTestCase):
    async def test_model_cannot_change_owned_browser(self):
        async def target(browser_id: str):
            return browser_id

        names = ["browser_action", "browser_observe", "browser_scrape", "session_start"]
        remote = [StructuredTool.from_function(coroutine=target, name=name, description=name) for name in names]
        tools = agent.browser_tools(remote, "owned-session")
        self.assertEqual({tool.name for tool in tools}, set(names[:3]))
        for tool in tools:
            self.assertEqual(await tool.ainvoke({"browser_id": "another-session"}), "owned-session")


@unittest.skipUnless(os.getenv("NOTTE_DEEPAGENTS_LIVE") == "1", "Opt-in cloud browser tests")
class DeepAgentsTests(unittest.IsolatedAsyncioTestCase):
    @unittest.skipUnless(os.getenv("NOTTE_DEEPAGENTS_MODEL_LIVE") == "1", "Opt-in actual model test")
    async def test_model_navigates_and_closes_browser(self):
        async with owned() as (client, ids):
            result = await agent.run("Visit https://example.com and report its page title.")
            self.assertIn("Example Domain", result["answer"])
            self.assertEqual(ids, [result["session_id"]])
        status = await closed(client, ids[0])
        self.assertTrue(
            any(
                step.get("type") == "execution_result"
                and step.get("value", {}).get("success") is True
                and step["value"].get("action", {}).get("type") == "goto"
                and step["value"]["action"].get("url", "").rstrip("/") == "https://example.com"
                for step in status.steps
            ),
            "The persisted browser history must prove successful navigation",
        )

    async def test_provider_401_closes_browser(self):
        requests = []

        class Unauthorized(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                requests.append({tool["name"] for tool in body["tools"]})
                body = json.dumps(
                    {
                        "type": "error",
                        "error": {"type": "authentication_error", "message": "Injected authentication failure"},
                    }
                ).encode()
                self.send_response(401)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Unauthorized)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with patch.dict(
                os.environ,
                {
                    "ANTHROPIC_BASE_URL": f"http://127.0.0.1:{server.server_port}",
                    "ANTHROPIC_API_KEY": "not-a-real-key",  # pragma: allowlist secret
                },
            ):
                async with owned():
                    with self.assertRaisesRegex(
                        RuntimeError,
                        r"^Deep Agents failed during agent execution: AnthropicAuthenticationError HTTP 401 \(session [0-9a-f-]{36}\)$",
                    ):
                        await agent.run("Visit https://example.com and read its title.")
            self.assertEqual(len(requests), 1, "The actual framework must reach the injected provider")
            self.assertFalse(requests[0] & {"glob", "grep", "execute"})
            self.assertIn("read_file", requests[0])
        finally:
            await asyncio.to_thread(server.shutdown)
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
