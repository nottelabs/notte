"""Real Notte browser tests; only the optional model case incurs OpenRouter charges."""

import asyncio
import base64
import json
import os
import re
import threading
import traceback
import unittest
from contextlib import nullcontext
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from typing import ClassVar
from unittest.mock import patch

import demo
import requests
from demo import run_demo
from notte_computer import NotteComputer
from notte_core.common.logging import logger
from notte_sdk import AsyncNotteClient
from openai import AsyncOpenAI
from openai.types.responses import ResponseComputerToolCall
from playwright.async_api import Browser


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
                    "message": "private-provider-body-fixture",
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


class TurnBoundary(BaseHTTPRequestHandler):
    requests = 0
    extra_call = False

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        type(self).requests += 1
        final = type(self).requests == 9 and not type(self).extra_call
        body = json.dumps(
            {
                "id": f"resp_{type(self).requests}",
                "object": "response",
                "created_at": 0,
                "model": "gpt-6.1-sol",
                "status": "completed",
                "output": [] if final else [call({"type": "screenshot"}).model_dump()],
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@unittest.skipUnless(os.getenv("NOTTE_API_KEY"), "Set NOTTE_API_KEY for live browser tests")
class ComputerLiveTests(unittest.IsolatedAsyncioTestCase):
    async def test_batched_actions_screenshot_and_permission(self):
        session = AsyncNotteClient().Session(max_duration_minutes=3)
        try:
            async with session:
                page = await session.page
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
                await page.set_content((Path(__file__).parents[1] / "fixtures/mouse.html").read_text())
                await computer.handle(call({"type": "move", "x": 400, "y": 100}))
                self.assertEqual(await page.locator("#pad").get_attribute("data-position"), "400,100")
                await computer.handle(call({"type": "double_click", "x": 400, "y": 100, "keys": []}))
                self.assertEqual(await page.locator("#pad").get_attribute("data-double-click"), "yes")
                await computer.handle(call({"type": "click", "button": "left", "x": 400, "y": 100, "keys": ["SHIFT"]}))
                self.assertEqual(await page.locator("#pad").get_attribute("data-shift"), "true")
                await computer.handle(call({"type": "click", "button": "left", "x": 400, "y": 100}))
                self.assertEqual(await page.locator("#pad").get_attribute("data-shift"), "false")
                await computer.handle(call({"type": "drag", "path": [{"x": 100, "y": 350}, {"x": 200, "y": 350}]}))
                self.assertEqual(await page.locator("#drag").get_attribute("data-position"), "200,350")
                await computer.handle(
                    call({"type": "scroll", "x": 800, "y": 600, "scroll_x": 0, "scroll_y": 200}, {"type": "wait"})
                )
                self.assertGreater(await page.evaluate("window.scrollY"), 0)
                self.assertEqual(len(set(computer.actions)), 9)
                for extra_call in (False, True):
                    TurnBoundary.requests = 0
                    TurnBoundary.extra_call = extra_call
                    server = ThreadingHTTPServer(("127.0.0.1", 0), TurnBoundary)
                    worker = threading.Thread(target=server.serve_forever, daemon=True)
                    worker.start()
                    try:
                        async with AsyncOpenAI(
                            api_key="test-invalid-key",  # pragma: allowlist secret
                            base_url=f"http://127.0.0.1:{server.server_port}",
                            max_retries=0,
                        ) as provider:
                            limited = NotteComputer(page, confirm=approve)
                            if extra_call:
                                with self.assertRaisesRegex(RuntimeError, "turn limit exceeded"):
                                    await limited.run(provider, "Check the screenshot")
                            else:
                                await limited.run(provider, "Check the screenshot")
                            self.assertEqual(len(limited.actions), 8)
                            self.assertEqual(TurnBoundary.requests, 9)
                    finally:
                        await asyncio.to_thread(server.shutdown)
                        server.server_close()
                        worker.join(timeout=5)
        finally:
            if session.session_id:
                await assert_closed(session.session_id)

    async def test_original_demo_provider_failure_closes_browser(self):
        for close_mode in ("normal", "reject", "timeout"):
            with self.subTest(close_mode=close_mode):
                await self.provider_failure(close_mode)

    async def provider_failure(self, close_mode):
        server = ThreadingHTTPServer(("127.0.0.1", 0), Unauthorized)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        before = Unauthorized.requests
        Unauthorized.payloads = []
        client, owned, messages = AsyncNotteClient(), [], []
        failure = None

        def create_session(**kwargs):
            session = client.Session(**kwargs)
            owned.append(session)
            return session

        async def fail_close(_browser, **_kwargs):
            if close_mode == "timeout":
                await asyncio.Event().wait()
            raise RuntimeError("private-close-body-fixture")

        try:
            with (
                patch.dict(
                    os.environ,
                    {
                        "OPENROUTER_API_KEY": "test-invalid-key",  # pragma: allowlist secret
                        "OPENAI_BASE_URL": f"http://127.0.0.1:{server.server_port}",
                    },
                ),
                patch.object(demo, "AsyncNotteClient", return_value=SimpleNamespace(Session=create_session)),
                patch.object(logger, "warning", side_effect=lambda message: messages.append(str(message))),
                patch.object(Browser, "close", fail_close) if close_mode != "normal" else nullcontext(),
            ):
                try:
                    await asyncio.wait_for(run_demo(), timeout=30)
                except Exception as error:
                    failure = error
        finally:
            try:
                if owned and owned[0].response is not None:
                    session = owned[0]
                    closed = False
                    try:
                        await assert_closed(session.session_id)
                        closed = True
                    finally:
                        if not closed:
                            await session.stop()
                            await assert_closed(session.session_id)
            finally:
                await asyncio.to_thread(server.shutdown)
                server.server_close()
                worker.join(timeout=5)

        self.assertIsInstance(failure, RuntimeError)
        self.assertRegex(str(failure), r"^Computer use failed: provider HTTP 401 \(session [a-f0-9-]+\)$")
        self.assertIsNone(failure.__cause__)
        rendered = "".join(traceback.format_exception(failure)) + repr(failure) + "\n".join(messages)
        self.assertNotIn("private-provider-body-fixture", rendered)
        self.assertNotIn("private-close-body-fixture", rendered)
        self.assertEqual(Unauthorized.requests - before, 2)
        first, second = Unauthorized.payloads
        self.assertEqual(first["tools"], [{"type": "computer"}])
        self.assertEqual(first["model"], "openai/gpt-6.1-sol")
        for payload in (first, second):
            self.assertNotIn("previous_response_id", payload)
            self.assertFalse(payload["store"])
            self.assertEqual(payload["provider"], {"allow_fallbacks": False})
        self.assertEqual(second["input"][0], first["input"][0])
        self.assertEqual(second["input"][1]["type"], "computer_call")
        self.assertEqual(second["input"][2]["call_id"], "call_test")
        self.assertEqual(second["input"][2]["output"]["detail"], "original")
        self.assertTrue(second["input"][2]["output"]["image_url"].startswith("data:image/png;base64,"))

    @unittest.skipUnless(os.getenv("OPENROUTER_API_KEY"), "Set OPENROUTER_API_KEY for the real model test")
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
