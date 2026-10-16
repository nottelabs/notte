import asyncio
import json
import os
import re
import secrets
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from contextlib import asynccontextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import notte_prime as example
import uvicorn
import verifiers.v1 as vf
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.server.mcpserver import MCPServer

LIVE = os.getenv("NOTTE_PRIME_LIVE") == "1"
FAKE_CREDENTIAL = "not-a-real-notte-credential"  # pragma: allowlist secret


@asynccontextmanager
async def native_tools(task, trace):
    """Use the framework's real MCP registration and authenticated state channel."""
    token = secrets.token_urlsafe(24)

    class StateHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.headers.get("Authorization") != f"Bearer {token}":
                self.send_error(401)
                return
            payload = trace.state.model_dump_json().encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_PUT(self):
            if self.headers.get("Authorization") != f"Bearer {token}":
                self.send_error(401)
                return
            trace.state = example.BrowserState.model_validate_json(self.rfile.read(int(self.headers["Content-Length"])))
            self.send_response(204)
            self.end_headers()

        def log_message(self, *_):
            pass

    state_server = ThreadingHTTPServer(("127.0.0.1", 0), StateHandler)
    thread = threading.Thread(target=state_server.serve_forever, daemon=True)
    thread.start()
    tools = task.toolsets(task.config)[0]
    mcp = MCPServer("Notte test")
    tools.register(mcp)
    app = mcp.streamable_http_app(json_response=True, stateless_http=True)
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="critical"))
    with patch.dict(
        os.environ,
        {
            "VF_STATE_URL": f"http://127.0.0.1:{state_server.server_port}/state",
            "VF_STATE_SECRET": token,
        },
    ):
        serving = asyncio.create_task(server.serve(sockets=[sock]))
        try:
            async with asyncio.timeout(10):
                while not server.started:
                    if serving.done():
                        serving.result()
                    await asyncio.sleep(0.01)
            async with streamable_http_client(f"http://127.0.0.1:{port}/mcp") as (read, write, *_):
                async with ClientSession(read, write) as client:
                    await client.initialize()
                    yield client
        finally:
            server.should_exit = True
            await asyncio.wait_for(serving, 10)
            state_server.shutdown()
            state_server.server_close()
            thread.join(timeout=2)


class BrowserTests(unittest.IsolatedAsyncioTestCase):
    @asynccontextmanager
    async def owned(self, failure=False):
        task = next(iter(example.NotteTaskset(vf.TasksetConfig(id="notte_prime"))))
        trace = vf.Trace(
            task=vf.TraceTask(type="BrowserTask", data=task.data),
            agent=vf.AgentInfo(config=vf.AgentConfig()),
            state=example.BrowserState(),
        )
        if LIVE:
            self.assertTrue(os.getenv("NOTTE_API_URL"), "Choose the browser API explicitly")
            client = example.NotteClient()
            session = client.Session(max_duration_minutes=3)
            started = []
            original_start = session.start

            def start():
                result = original_start()
                started.append(session.session_id)
                return result

            session.start = start
        else:
            started, stopped = [], []
            session = SimpleNamespace(
                response=object(),
                session_id="11111111-1111-4111-8111-111111111111",
                start=lambda: started.append("owned"),
                stop=lambda: stopped.append("owned"),
                cdp_url=lambda: f"wss://notte.example.invalid/?token={FAKE_CREDENTIAL}",
            )
            client = SimpleNamespace(Session=lambda **_: session)
        with patch.object(example, "NotteClient", return_value=SimpleNamespace(Session=lambda **_: session)):
            try:
                await task.setup(trace, None)
                self.assertEqual(trace.state.session_id, session.session_id)
                if LIVE:
                    yield task, trace
                else:
                    page = SimpleNamespace(
                        goto=AsyncMock(side_effect=RuntimeError(FAKE_CREDENTIAL) if failure else None),
                        title=AsyncMock(return_value="Example Domain"),
                        url="https://example.com/",
                    )
                    browser = SimpleNamespace(
                        contexts=[SimpleNamespace(new_page=AsyncMock(return_value=page))],
                        close=AsyncMock(),
                    )
                    driver = AsyncMock()
                    driver.__aenter__.return_value.chromium.connect_over_cdp = AsyncMock(return_value=browser)
                    with patch.object(example, "async_playwright", return_value=driver):
                        yield task, trace
                    browser.close.assert_awaited_once()
            finally:
                await task.finalize(trace, None)
                self.assertEqual(len(started), 1)
                self.assertEqual(trace.state.cdp_url, "")
                if LIVE:
                    async with asyncio.timeout(15):
                        while (await asyncio.to_thread(client.sessions.status, session.session_id)).status != "closed":
                            await asyncio.sleep(0.5)
                else:
                    self.assertEqual(stopped, started)

    async def test_native_mcp_browser_and_reward(self):
        async with self.owned() as (task, trace):
            async with native_tools(task, trace) as client:
                tools = (await client.list_tools()).tools
                self.assertEqual([tool.name for tool in tools], ["read_page"])
                schema = json.dumps(tools[0].input_schema)
                self.assertNotIn("session_id", schema)
                self.assertNotIn("cdp_url", schema)
                result = await client.call_tool("read_page", {"url": "https://example.com"})
                self.assertFalse(result.is_error)
                self.assertIn("Example Domain", result.content[0].text)
            await task.score(trace)
            self.assertEqual(trace.rewards["title_matches"].score, 1)
            serialized = trace.model_dump_json()
            self.assertNotIn("cdp_url", serialized)
            self.assertNotIn(FAKE_CREDENTIAL, serialized)
            if os.getenv("NOTTE_API_KEY"):
                self.assertNotIn(os.environ["NOTTE_API_KEY"], serialized)

    async def test_navigation_error_is_safe_and_owned_browser_closes(self):
        async with self.owned(failure=True) as (task, trace):
            async with native_tools(task, trace) as client:
                result = await client.call_tool("read_page", {"url": "http://127.0.0.1:1"})
                self.assertTrue(result.is_error)
                self.assertIn("The browser task failed", result.content[0].text)
                self.assertNotIn(FAKE_CREDENTIAL, result.content[0].text)
            await task.score(trace)
            self.assertEqual(trace.rewards["title_matches"].score, 0)

    async def test_reward_rejects_another_page_with_the_expected_title(self):
        task = next(iter(example.NotteTaskset(vf.TasksetConfig())))
        trace = SimpleNamespace(state=example.BrowserState(title="Example Domain", url="https://different.example"))
        self.assertEqual(await task.title_matches(trace), 0)

    async def test_cancelled_creation_finishes_and_closes_before_propagating(self):
        task = next(iter(example.NotteTaskset(vf.TasksetConfig())))
        entered, release = threading.Event(), threading.Event()
        stopped = []

        class Session:
            response = None

            def start(self):
                entered.set()
                if not release.wait(5):
                    raise TimeoutError("Test did not release creation")
                self.response = object()

            @property
            def session_id(self):
                if self.response is None:
                    raise ValueError("Session has not started")
                return "owned"

            def stop(self):
                stopped.append(self.session_id)

        session = Session()
        with patch.object(example, "NotteClient", return_value=SimpleNamespace(Session=lambda **_: session)):
            starting = asyncio.create_task(task.setup(SimpleNamespace(state=example.BrowserState()), None))
            try:
                self.assertTrue(await asyncio.to_thread(entered.wait, 5))
                starting.cancel()
                await asyncio.sleep(0)
                self.assertFalse(starting.done())
            finally:
                release.set()
            with self.assertRaises(asyncio.CancelledError):
                await asyncio.wait_for(starting, 5)
        self.assertEqual(stopped, ["owned"])
        self.assertIsNone(task.session)

    async def test_failed_creation_preserves_safe_error_and_clears_owner(self):
        task = next(iter(example.NotteTaskset(vf.TasksetConfig())))

        class Session:
            response = None

            def start(self):
                raise RuntimeError(FAKE_CREDENTIAL)

            @property
            def session_id(self):
                raise ValueError("Session has not started")

            def stop(self):
                raise AssertionError("An unstarted browser must not be stopped")

        with patch.object(example, "NotteClient", return_value=SimpleNamespace(Session=lambda **_: Session())):
            with self.assertRaisesRegex(RuntimeError, "^Could not prepare the rollout browser$"):
                await task.setup(SimpleNamespace(state=example.BrowserState()), None)
        self.assertIsNone(task.session)

    @unittest.skipUnless(LIVE, "Opt-in real browser rollout")
    async def test_full_framework_provider_failure_closes_its_browser(self):
        """Task finalizers alone are skipped on provider failure in Verifiers 0.4."""
        self.assertTrue(os.getenv("NOTTE_API_KEY"))
        self.assertTrue(os.getenv("NOTTE_API_URL"))
        requests = []

        class Provider(BaseHTTPRequestHandler):
            def do_POST(self):
                requests.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                self.send_response(401)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"error":{"type":"authentication_error","message":"Injected rejection"}}')

            def log_message(self, *_):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Provider)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        client, ids = example.NotteClient(), []
        try:
            with tempfile.TemporaryDirectory() as directory:
                command = [
                    sys.executable,
                    "-c",
                    "from verifiers.v1.cli.eval.main import main; main()",
                    "notte_prime",
                    "--env.agent.runtime.type",
                    "subprocess",
                    "--env.agent.max_turns",
                    "3",
                    "--env.agent.timeout.setup",
                    "60",
                    "--env.agent.timeout.rollout",
                    "60",
                    "--no-push",
                    "--no-rich",
                    "-n",
                    "1",
                    "-c",
                    "1",
                    "--model",
                    "local-test",
                    "--client.base_url",
                    f"http://127.0.0.1:{server.server_port}/v1",
                    "--client.api_key_var",
                    "PRIME_LOCAL_TEST_KEY",
                    "--output_dir",
                    directory,
                ]
                try:
                    result = await asyncio.to_thread(
                        subprocess.run,
                        command,
                        cwd=Path(__file__).parent,
                        env={**os.environ, "PRIME_LOCAL_TEST_KEY": FAKE_CREDENTIAL},
                        capture_output=True,
                        text=True,
                        timeout=180,
                    )
                except subprocess.TimeoutExpired as error:
                    captured = (error.stdout or b"") + (error.stderr or b"")
                    ids = re.findall(r"\[Session\]\s+([0-9a-f-]{36}) started", captured.decode())
                    self.fail("The framework exceeded its test deadline; child output withheld")
                output = result.stdout + result.stderr
                ids = re.findall(r"\[Session\]\s+([0-9a-f-]{36}) started", output)
                self.assertEqual(result.returncode, 0, "The framework CLI failed; child output withheld")
                self.assertEqual(len(requests), 1, "The real framework must reach the injected provider")
                self.assertEqual(len(ids), 1)
                trace_file = next(Path(directory).glob("*/traces.jsonl"))
                episode = json.loads(trace_file.read_text().splitlines()[0])
                self.assertFalse(episode["ok"])
                self.assertEqual(len(episode["traces"]), 1)
                trace = episode["traces"][0]
                self.assertFalse(trace["ok"])
                self.assertIn("ProviderError", [error["type"] for error in trace["errors"]])
                for payload in [output, json.dumps(requests), trace_file.read_text()]:
                    self.assertNotIn(os.environ["NOTTE_API_KEY"], payload)
                for session_id in ids:
                    async with asyncio.timeout(15):
                        while (await asyncio.to_thread(client.sessions.status, session_id)).status != "closed":
                            await asyncio.sleep(0.5)
        finally:
            # Keep a failing assertion from leaking its test-owned resource.
            for session_id in ids:
                status = await asyncio.to_thread(client.sessions.status, session_id)
                if status.status != "closed":
                    await asyncio.to_thread(client.sessions.stop, session_id)
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
