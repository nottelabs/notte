"""Run with `python -m unittest discover -s python -p test_live.py -v`."""

import asyncio
import json
import os
import re
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

import requests
from anthropic.types.beta import BetaToolUseBlock
from demo import run_demo
from notte_computer import NotteComputer
from notte_sdk import NotteClient


async def assert_closed(session_id: str) -> None:
    async with asyncio.timeout(15):
        while True:
            response = await asyncio.to_thread(
                requests.get,
                f"{os.getenv('NOTTE_API_URL', 'https://api.notte.cc').rstrip('/')}/sessions/{session_id}",
                headers={"Authorization": f"Bearer {os.environ['NOTTE_API_KEY']}"},
                timeout=15,
            )
            response.raise_for_status()
            state = response.json()["status"]
            if state == "closed":
                return
            if state != "active":
                raise AssertionError(f"Unexpected session state: {state}")
            await asyncio.sleep(0.5)


def tool(name: str, **input) -> BetaToolUseBlock:
    return BetaToolUseBlock(id=f"toolu_{name}", type="tool_use", toolset_name="computer", name=name, input=input)


class Unauthorized(BaseHTTPRequestHandler):
    requests = 0

    def do_POST(self):
        type(self).requests += 1
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        body = json.dumps(
            {
                "type": "error",
                "error": {
                    "type": "authentication_error",
                    "message": "Test credential rejected",
                },
            }
        ).encode()
        self.send_response(401)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@unittest.skipUnless(os.getenv("NOTTE_API_KEY"), "Set NOTTE_API_KEY for live browser tests")
class ComputerLiveTests(unittest.IsolatedAsyncioTestCase):
    async def test_native_tool_protocol_and_permission(self):
        client = NotteClient()
        session = client.Session(max_duration_minutes=3)
        try:
            async with session:
                page = await session.apage
                await page.goto("about:blank")
                await page.set_viewport_size({"width": 1024, "height": 768})
                await page.set_content(
                    "<form onsubmit=\"event.preventDefault();document.querySelector('output').textContent='Accepted'\"><input style=\"position:absolute;left:30px;top:30px;width:300px;height:40px\"><output></output></form>"
                )
                async with NotteComputer(page, confirm=lambda context: True) as computer:
                    shot = await computer.tool_result(tool("screenshot"))
                    self.assertEqual(shot["toolset_name"], "computer")
                    self.assertEqual(shot["content"][0]["type"], "image")
                    for call in [
                        tool("left_click", coordinate=[100, 50]),
                        tool("type", text="native-protocol"),
                        tool("key", text="Return"),
                    ]:
                        result = await computer.tool_result(call)
                        self.assertFalse(result.get("is_error"), "Native tool dispatch failed")
                    self.assertEqual(await page.locator("input").input_value(), "native-protocol")
                    self.assertEqual(await page.locator("output").inner_text(), "Accepted")
                    invalid = await computer.tool_result(tool("left_click", coordinate=[1024, 0]))
                    self.assertTrue(invalid["is_error"])
                    disabled = await computer.tool_result(tool("scroll", direction="down", amount=1))
                    self.assertTrue(disabled["is_error"])
                async with NotteComputer(page, confirm=lambda context: False) as denied:
                    result = await denied.tool_result(tool("type", text="should-not-appear"))
                    self.assertTrue(result["is_error"])
                    self.assertEqual(await page.locator("input").input_value(), "native-protocol")
        finally:
            if session.session_id:
                await assert_closed(session.session_id)

    async def test_original_demo_provider_failure_closes_browser(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), Unauthorized)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        before = Unauthorized.requests
        try:
            with patch.dict(
                os.environ,
                {
                    "ANTHROPIC_API_KEY": "test-invalid-key",
                    "ANTHROPIC_BASE_URL": f"http://127.0.0.1:{server.server_port}",
                },
            ):
                with self.assertRaisesRegex(RuntimeError, r"Computer use failed \(session [a-f0-9-]+\)") as failure:
                    await run_demo()
            self.assertGreater(Unauthorized.requests, before)
            session_id = re.search(r"session ([a-f0-9-]+)", str(failure.exception))[1]
            await assert_closed(session_id)
        finally:
            await asyncio.to_thread(server.shutdown)
            server.server_close()
            worker.join(timeout=5)

    @unittest.skipUnless(os.getenv("ANTHROPIC_API_KEY"), "Set ANTHROPIC_API_KEY for the real model test")
    async def test_original_demo_real_model(self):
        session_id = None
        try:
            result = await run_demo()
            session_id = result["session_id"]
            self.assertEqual(result["output"], "Accepted")
            self.assertTrue({"screenshot", "left_click", "type", "key"} <= set(result["calls"]))
        except RuntimeError as error:
            match = re.search(r"session ([a-f0-9-]+)", str(error))
            if match:
                session_id = match[1]
            raise
        finally:
            if session_id:
                await assert_closed(session_id)
