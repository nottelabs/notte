import asyncio
import io
import json
import logging
import os
import struct
import threading
import traceback
import unittest
from contextlib import contextmanager, nullcontext
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

import httpx
from demo import run_demo
from notte_computer import BrowserActions, Screenshots
from notte_sdk import AsyncNotteClient
from oagi import AsyncDefaultAgent
from oagi.logging import get_logger
from oagi.types.models import Action
from playwright.async_api import BrowserType


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
                            "message": "PRIVATE_PROVIDER_FIXTURE",
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


def journal(event, session_id):
    if path := os.getenv("OAGI_OWNERSHIP_JOURNAL"):
        try:
            with open(path, "a") as output:
                output.write(json.dumps({"event": event, "session_id": session_id}) + "\n")
                output.flush()
                os.fsync(output.fileno())
        except OSError:
            print("Ownership journal unavailable")


async def assert_closed(test, session_id):
    root = (os.getenv("NOTTE_API_URL") or "https://api.notte.cc").rstrip("/")
    headers = {"Authorization": f"Bearer {os.environ['NOTTE_API_KEY']}"}
    async with httpx.AsyncClient(timeout=15) as client:

        async def wait_closed():
            async with asyncio.timeout(15):
                while True:
                    response = await client.get(f"{root}/sessions/{session_id}", headers=headers)
                    test.assertEqual(response.status_code, 200)
                    if response.json()["status"] == "closed":
                        journal("closed", session_id)
                        return
                    await asyncio.sleep(0.5)

        try:
            await wait_closed()
        except BaseException:
            response = await client.delete(f"{root}/sessions/{session_id}/stop", headers=headers)
            test.assertTrue(response.is_success, "Owned fallback stop failed")
            await wait_closed()
            raise


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
            async with AsyncNotteClient().Session(
                max_duration_minutes=3, viewport_width=1024, viewport_height=768
            ) as session:
                session_id = session.session_id
                journal("allocated", session_id)
                page = await session.page
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
            async with AsyncNotteClient().Session(
                max_duration_minutes=3, viewport_width=1024, viewport_height=768
            ) as session:
                session_id = session.session_id
                journal("allocated", session_id)
                page = await session.page
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
        for mode in ("normal", "reject", "timeout"):
            with self.subTest(close=mode):
                client = AsyncNotteClient()
                start = client.sessions.start
                connect = BrowserType.connect_over_cdp
                ids, closes = [], []
                failure = None
                messages = io.StringIO()
                logger = logging.getLogger("oagi")

                async def tracked(*args, **kwargs):
                    response = await start(*args, **kwargs)
                    ids.append(response.session_id)
                    journal("allocated", response.session_id)
                    return response

                async def connected(browser_type, *args, **kwargs):
                    browser = await connect(browser_type, *args, **kwargs)
                    close = browser.close

                    async def disconnect():
                        await close()
                        closes.append(True)
                        if mode == "timeout":
                            await asyncio.Future()
                        raise RuntimeError("PRIVATE_CLOSE_FIXTURE")

                    browser.close = disconnect
                    return browser

                with (
                    provider(failure=True) as (url, state),
                    patch.dict(
                        os.environ,
                        {
                            "OAGI_BASE_URL": url,
                            "OAGI_API_KEY": "fixture-token",  # pragma: allowlist secret
                            "OAGI_LOG": "INFO",
                        },
                    ),
                    patch("demo.AsyncNotteClient", return_value=client),
                    patch.object(client.sessions, "start", side_effect=tracked),
                    patch.object(BrowserType, "connect_over_cdp", new=connected) if mode != "normal" else nullcontext(),
                ):
                    get_logger("privacy-test")
                    self.assertEqual(
                        logger.getEffectiveLevel(), logging.INFO, "Initialize SDK diagnostics before the demo"
                    )
                    streams = [
                        (handler, handler.stream)
                        for handler in logger.handlers
                        if isinstance(handler, logging.StreamHandler)
                    ]
                    for handler, _ in streams:
                        handler.setStream(messages)
                    try:
                        try:
                            await asyncio.wait_for(run_demo(), timeout=45)
                        except Exception as error:
                            failure = error
                    finally:
                        try:
                            for session_id in ids:
                                await assert_closed(self, session_id)
                        finally:
                            for handler, stream in streams:
                                handler.setStream(stream)
                self.assertEqual(len(ids), 1, "Expected one owned demo browser")
                self.assertIsInstance(failure, RuntimeError)
                self.assertIsNone(failure.__cause__)
                self.assertTrue(failure.__suppress_context__)
                self.assertIn("provider HTTP 401", str(failure))
                diagnostic = "".join(traceback.format_exception(failure)) + messages.getvalue()
                self.assertFalse("PRIVATE_PROVIDER_FIXTURE" in diagnostic, "Private provider diagnostics leaked")
                self.assertFalse("PRIVATE_CLOSE_FIXTURE" in diagnostic, "Private close diagnostics leaked")
                self.assertEqual(closes, [] if mode == "normal" else [True])
                self.assertEqual(len(state["uploads"]), 1)
                self.assertEqual(len(state["requests"]), 1)

    async def test_native_agent_failure_is_not_reported_as_success(self):
        session_id = None
        try:
            async with AsyncNotteClient().Session(
                max_duration_minutes=3, viewport_width=1024, viewport_height=768
            ) as session:
                session_id = session.session_id
                journal("allocated", session_id)
                page = await session.page
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

    async def test_demo_reports_disconnect_failure_inside_caller_except(self):
        client = AsyncNotteClient()
        start = client.sessions.start
        connect = BrowserType.connect_over_cdp
        ids, completed, closes = [], [], []

        async def tracked(*args, **kwargs):
            response = await start(*args, **kwargs)
            ids.append(response.session_id)
            journal("allocated", response.session_id)
            return response

        async def connected(browser_type, *args, **kwargs):
            browser = await connect(browser_type, *args, **kwargs)
            close = browser.close

            async def disconnect():
                await close()
                closes.append(True)
                raise RuntimeError("PRIVATE_CLOSE_FIXTURE")

            browser.close = disconnect
            return browser

        async def execute(_agent, _instruction, *, action_handler, image_provider):
            page = action_handler.page
            self.assertGreater(len((await image_provider()).read()), 0)
            code = (await page.locator("p").inner_text()).removeprefix("Code: ")
            await page.locator("input").fill(code)
            await page.locator("input").press("Enter")
            self.assertEqual(await page.locator("output").inner_text(), "Accepted")
            completed.append(True)
            return True

        try:
            with (
                patch.dict(os.environ, {"OAGI_API_KEY": "fixture-token"}),  # pragma: allowlist secret
                patch("demo.AsyncNotteClient", return_value=client),
                patch.object(client.sessions, "start", side_effect=tracked),
                patch.object(BrowserType, "connect_over_cdp", new=connected),
                patch.object(AsyncDefaultAgent, "execute", new=execute),
            ):
                try:
                    raise ValueError("Unrelated caller exception")
                except ValueError:
                    with self.assertRaises(RuntimeError) as caught:
                        async with asyncio.timeout(45):
                            await run_demo()
            self.assertIn("OpenAGI failed: RuntimeError", str(caught.exception))
            self.assertIsNone(caught.exception.__cause__)
            self.assertTrue(caught.exception.__suppress_context__)
            self.assertNotIn("PRIVATE_CLOSE_FIXTURE", str(caught.exception))
            self.assertEqual(completed, [True])
            self.assertEqual(closes, [True])
            self.assertEqual(len(ids), 1)
        finally:
            for session_id in ids:
                await assert_closed(self, session_id)

    async def test_actions_reject_invalid_geometry_counts_and_permissions(self):
        session_id = None
        try:
            async with AsyncNotteClient().Session(
                max_duration_minutes=3, viewport_width=1024, viewport_height=768
            ) as session:
                session_id = session.session_id
                journal("allocated", session_id)
                page = await session.page
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
