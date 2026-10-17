import asyncio
import json
import os
import re
import struct
import threading
import unittest
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

import httpx
from demo import run_demo
from notte_computer import BrowserActions, Screenshots
from notte_sdk import NotteClient
from oagi import AsyncDefaultAgent
from oagi.types.models import Action
from openai import AuthenticationError


@contextmanager
def provider(*, failure=False, refusal=False):
    state = {"uploads": [], "requests": []}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def send_json(self, value, status=200):
            data = json.dumps(value).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):  # noqa: N802 - HTTP handler interface
            if self.path != "/v1/file/upload":
                self.send_json({}, 404)
                return
            url = f"http://127.0.0.1:{self.server.server_port}/image/{len(state['uploads'])}"
            self.send_json(
                {
                    "url": url,
                    "download_url": url,
                    "uuid": "fixture",
                    "expires_at": 2_000_000_000,
                    "file_expires_at": 2_000_000_000,
                }
            )

        def do_PUT(self):  # noqa: N802
            image = self.rfile.read(int(self.headers["Content-Length"]))
            state["uploads"].append(image)
            self.send_json({})

        def do_POST(self):  # noqa: N802
            if self.path != "/v1/chat/completions":
                self.send_json({}, 404)
                return
            request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            state["requests"].append(request)
            if failure:
                self.send_json(
                    {
                        "error": {
                            "message": "Fixture authentication refused",
                            "type": "authentication_error",
                            "code": "invalid_api_key",
                        }
                    },
                    401,
                )
                return
            actions = (
                "fail()"
                if refusal
                else (
                    "click(117,104) & type(orbit-test) & hotkey(enter)" if len(state["requests"]) == 1 else "finish()"
                )
            )
            self.send_json(
                {
                    "id": "fixture",
                    "object": "chat.completion",
                    "created": 0,
                    "model": "lux-actor-1",
                    "choices": [
                        {
                            "index": 0,
                            "finish_reason": "stop",
                            "message": {
                                "role": "assistant",
                                "content": f"<|action_start|>{actions}<|action_end|>",
                            },
                        }
                    ],
                }
            )

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


async def assert_closed(test, session_id):
    async with httpx.AsyncClient(timeout=15) as client:
        for attempt in range(30):
            response = await client.get(
                f"{os.getenv('NOTTE_API_URL', 'https://api.notte.cc')}/sessions/{session_id}",
                headers={"Authorization": f"Bearer {os.environ['NOTTE_API_KEY']}"},
            )
            test.assertEqual(response.status_code, 200)
            if response.json()["status"] == "closed":
                return
            await asyncio.sleep(0.5)
    test.fail(f"Owned session {session_id} remained active")


async def fixture(page):
    await page.route("**/*", lambda route: route.abort())
    await page.goto("about:blank")
    await page.set_viewport_size({"width": 1024, "height": 768})
    await page.set_content(
        "<form onsubmit=\"event.preventDefault();document.querySelector('output').textContent="
        "document.querySelector('input').value==='orbit-test'?'Accepted':'Rejected'\">"
        '<input aria-label="Code" style="position:absolute;left:40px;top:60px;width:300px;height:40px">'
        "<button>Submit</button></form><output></output>"
    )


async def allow(_):
    return True


class LiveTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        if not os.getenv("NOTTE_API_KEY"):
            raise RuntimeError("Set NOTTE_API_KEY before running live OpenAGI tests")

    async def test_mouse_actions_and_repeated_keys_reach_the_browser(self):
        session_id = None
        try:
            async with NotteClient().Session(max_duration_minutes=3) as session:
                session_id = session.session_id
                page = await session.apage
                await fixture(page)
                await page.set_content(
                    '<body style="height:2200px"><input><input><script>window.events=[];'
                    "for(const type of ['click','contextmenu','mousemove','keydown']){"
                    "document.addEventListener(type,e=>{if(type==='contextmenu')e.preventDefault();"
                    "window.events.push({type,detail:e.detail,button:e.button,buttons:e.buttons,key:e.key});});}"
                    "</script></body>"
                )
                screenshots = Screenshots(page)
                self.assertEqual((await screenshots()).read(), (await screenshots.last_image()).read())
                await BrowserActions(page, confirm=allow)(
                    [
                        Action(type="left_double", argument="100,100"),
                        Action(type="left_triple", argument="100,100"),
                        Action(type="right_single", argument="100,100"),
                        Action(type="drag", argument="100,100,300,300"),
                        Action(type="hotkey", argument="tab", count=2),
                        Action(type="scroll", argument="500,500,down"),
                    ]
                )
                await page.wait_for_function("window.scrollY > 0")
                events = await page.evaluate("window.events")
                for detail in (2, 3):
                    self.assertTrue(any(event["type"] == "click" and event["detail"] == detail for event in events))
                self.assertTrue(any(event["type"] == "contextmenu" and event["button"] == 2 for event in events))
                self.assertTrue(any(event["type"] == "mousemove" and event["buttons"] == 1 for event in events))
                self.assertEqual(sum(event["type"] == "keydown" and event["key"] == "Tab" for event in events), 2)
        finally:
            if session_id:
                await assert_closed(self, session_id)

    async def test_native_agent_uploads_screenshots_and_completes_form(self):
        session_id = None
        try:
            async with NotteClient().Session(max_duration_minutes=3) as session:
                session_id = session.session_id
                page = await session.apage
                await fixture(page)
                with provider() as (url, state):
                    agent = AsyncDefaultAgent(api_key="fixture-token", base_url=url, max_steps=3, step_delay=0)
                    completed = await agent.execute(
                        "Enter orbit-test and submit",
                        action_handler=BrowserActions(page, confirm=allow),
                        image_provider=Screenshots(page),
                    )
                self.assertTrue(completed)
                self.assertEqual(await page.locator("input").input_value(), "orbit-test")
                self.assertEqual(await page.locator("output").inner_text(), "Accepted")
                self.assertEqual(len(state["requests"]), 2)
                self.assertEqual(len(state["uploads"]), 2)
                for image in state["uploads"]:
                    self.assertEqual(image[:8], bytes((137, 80, 78, 71, 13, 10, 26, 10)))
                    self.assertEqual(struct.unpack(">II", image[16:24]), (1024, 768))
                for index, request in enumerate(state["requests"]):
                    self.assertEqual(request["model"], "lux-actor-1")
                    self.assertIn(f"/image/{index}", json.dumps(request["messages"]))
        finally:
            if session_id:
                await assert_closed(self, session_id)

    async def test_real_sdk_http_401_closes_demo_browser(self):
        with (
            provider(failure=True) as (url, state),
            patch.dict(os.environ, {"OAGI_BASE_URL": url, "OAGI_API_KEY": "fixture-token"}),
        ):
            with self.assertRaises(RuntimeError) as result:
                await run_demo()
        error = result.exception
        self.assertIsInstance(error.__cause__, AuthenticationError)
        self.assertIn("provider HTTP 401", str(error))
        session_id = re.search(r"session ([a-f0-9-]{36})", str(error))
        self.assertIsNotNone(session_id)
        await assert_closed(self, session_id.group(1))
        self.assertEqual(len(state["uploads"]), 1)
        self.assertEqual(len(state["requests"]), 1)

    async def test_native_agent_failure_is_not_reported_as_success(self):
        session_id = None
        try:
            async with NotteClient().Session(max_duration_minutes=3) as session:
                session_id = session.session_id
                page = await session.apage
                await fixture(page)
                with provider(refusal=True) as (url, state):
                    agent = AsyncDefaultAgent(api_key="fixture-token", base_url=url, max_steps=2, step_delay=0)
                    with self.assertRaisesRegex(PermissionError, "failure or human review"):
                        await agent.execute("Refuse this task", BrowserActions(page, confirm=allow), Screenshots(page))
                self.assertEqual(await page.locator("input").input_value(), "")
                self.assertEqual(len(state["requests"]), 1)
        finally:
            if session_id:
                await assert_closed(self, session_id)

    async def test_actions_reject_invalid_geometry_counts_and_permissions(self):
        session_id = None
        try:
            async with NotteClient().Session(max_duration_minutes=3) as session:
                session_id = session.session_id
                page = await session.apage
                await fixture(page)
                actions = BrowserActions(page, confirm=allow)
                with self.assertRaises(ValueError):
                    await actions([Action(type="click", argument="1001, 100")])
                with self.assertRaises(ValueError):
                    await actions([Action(type="hotkey", argument="enter", count=9)])
                with self.assertRaises(PermissionError):
                    await actions([Action(type="call_user", argument="review")])
                with self.assertRaises(ValueError):
                    await actions([Action(type="finish", argument=""), Action(type="type", argument="unexpected")])

                async def refuse(_):
                    return False

                with self.assertRaises(PermissionError):
                    await BrowserActions(page, confirm=refuse)([Action(type="type", argument="unexpected")])
                self.assertEqual(await page.locator("input").input_value(), "")
                await actions(
                    [
                        Action(type="click", argument="117,104"),
                        Action(type="type", argument="orbit-test"),
                        Action(type="hotkey", argument="enter"),
                    ]
                )
                self.assertEqual(await page.locator("output").inner_text(), "Accepted")
        finally:
            if session_id:
                await assert_closed(self, session_id)


if __name__ == "__main__":
    unittest.main()
