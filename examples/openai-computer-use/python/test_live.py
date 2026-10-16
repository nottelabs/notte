"""Real Notte browser tests; only the optional model case incurs OpenAI charges."""

import asyncio
import base64
import json
import os
import re
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import ClassVar
from unittest.mock import patch

import requests
from demo import run_demo
from notte_computer import NotteComputer
from notte_sdk import NotteClient
from openai import AuthenticationError
from openai.types.responses import ResponseComputerToolCall


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


def call(*actions, safety_checks=None) -> ResponseComputerToolCall:
    return ResponseComputerToolCall.model_validate(
        {
            "id": "cu_test",
            "call_id": "call_test",
            "type": "computer_call",
            "status": "completed",
            "actions": list(actions),
            "pending_safety_checks": safety_checks or [],
        }
    )


class Unauthorized(BaseHTTPRequestHandler):
    requests = 0
    payloads: ClassVar[list[dict]] = []

    def do_POST(self):
        type(self).requests += 1
        type(self).payloads.append(json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0)))))
        if len(type(self).payloads) == 1:
            body = json.dumps(
                {
                    "id": "resp_protocol",
                    "object": "response",
                    "created_at": 0,
                    "model": "gpt-6.1-sol",
                    "status": "completed",
                    "output": [call({"type": "screenshot"}).model_dump()],
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        body = json.dumps(
            {
                "error": {
                    "type": "invalid_request_error",
                    "message": "Test credential rejected",
                    "code": "invalid_api_key",
                }
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
    async def test_batched_actions_screenshot_and_permission(self):
        session = NotteClient().Session(max_duration_minutes=3)
        try:
            async with session:
                page = await session.apage
                await page.goto("about:blank")
                await page.set_viewport_size({"width": 1024, "height": 768})
                await page.set_content(
                    "<form onsubmit=\"event.preventDefault();document.querySelector('output').textContent='Accepted'\"><input style=\"position:absolute;left:30px;top:30px;width:300px;height:40px\"><output></output></form>"
                )

                async def approve(action):
                    return True

                computer = NotteComputer(page, confirm=approve)
                result = await computer.handle(
                    call(
                        {"type": "screenshot"},
                        {"type": "click", "button": "left", "x": 100, "y": 50},
                        {"type": "type", "text": "native-protocol"},
                        {"type": "keypress", "keys": ["ENTER"]},
                    )
                )
                self.assertEqual(result["call_id"], "call_test")
                self.assertEqual(result["type"], "computer_call_output")
                image = base64.b64decode(result["output"]["image_url"].split(",", 1)[1])
                self.assertEqual(image[:8], b"\x89PNG\r\n\x1a\n")
                self.assertEqual(int.from_bytes(image[16:20]), 1024)
                self.assertEqual(int.from_bytes(image[20:24]), 768)
                self.assertEqual(await page.locator("input").input_value(), "native-protocol")
                self.assertEqual(await page.locator("output").inner_text(), "Accepted")
                await computer.handle(
                    call(
                        {"type": "move", "x": 20, "y": 200},
                        {"type": "double_click", "x": 100, "y": 50, "keys": []},
                        {"type": "scroll", "x": 20, "y": 200, "scroll_x": 0, "scroll_y": 100},
                        {"type": "drag", "path": [{"x": 100, "y": 50}, {"x": 120, "y": 50}]},
                        {"type": "wait"},
                    )
                )
                self.assertEqual(len(set(computer.actions)), 9)
                with self.assertRaisesRegex(ValueError, "Coordinates outside"):
                    await computer.handle(call({"type": "click", "button": "left", "x": 1024, "y": 0}))
                with self.assertRaisesRegex(PermissionError, "human safety review"):
                    await computer.handle(
                        call(
                            {"type": "type", "text": "denied"},
                            safety_checks=[{"id": "check_1", "code": "unsafe", "message": "Review required"}],
                        )
                    )

                async def deny(action):
                    return False

                with self.assertRaisesRegex(PermissionError, "refused"):
                    await NotteComputer(page, confirm=deny).handle(call({"type": "type", "text": "denied"}))
                self.assertEqual(await page.locator("input").input_value(), "native-protocol")
        finally:
            if session.session_id:
                await assert_closed(session.session_id)

    async def test_original_demo_provider_failure_closes_browser(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), Unauthorized)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        before = Unauthorized.requests
        Unauthorized.payloads = []
        try:
            with (
                patch.dict(
                    os.environ,
                    {
                        "OPENAI_API_KEY": "test-invalid-key",  # pragma: allowlist secret
                        "OPENAI_BASE_URL": f"http://127.0.0.1:{server.server_port}",
                    },
                ),
                self.assertRaisesRegex(
                    RuntimeError, r"Computer use failed: provider HTTP 401 \(session [a-f0-9-]+\)"
                ) as failure,
            ):
                await run_demo()
            self.assertEqual(Unauthorized.requests - before, 2)
            first, second = Unauthorized.payloads
            self.assertEqual(first["tools"], [{"type": "computer"}])
            self.assertEqual(second["previous_response_id"], "resp_protocol")
            self.assertEqual(second["input"][0]["call_id"], "call_test")
            self.assertEqual(second["input"][0]["output"]["detail"], "original")
            self.assertTrue(second["input"][0]["output"]["image_url"].startswith("data:image/png;base64,"))
            self.assertIsInstance(failure.exception.__cause__, AuthenticationError)
            session_id = re.search(r"session ([a-f0-9-]+)", str(failure.exception))[1]
            await assert_closed(session_id)
        finally:
            await asyncio.to_thread(server.shutdown)
            server.server_close()
            worker.join(timeout=5)

    @unittest.skipUnless(os.getenv("OPENAI_API_KEY"), "Set OPENAI_API_KEY for the real model test")
    async def test_original_demo_real_model(self):
        session_id = None
        try:
            result = await run_demo()
            session_id = result["session_id"]
            self.assertEqual(result["output"], "Accepted")
            self.assertIn("type", result["actions"])
            self.assertTrue({"click", "keypress"} & set(result["actions"]))
        except RuntimeError as error:
            match = re.search(r"session ([a-f0-9-]+)", str(error))
            if match:
                session_id = match[1]
            raise
        finally:
            if session_id:
                await assert_closed(session_id)
