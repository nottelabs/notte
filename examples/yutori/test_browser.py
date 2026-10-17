import asyncio
import base64
import io
import json
import os
import time
import unittest
from contextlib import contextmanager
from unittest.mock import patch

import main as demo
import requests
from notte_sdk import NotteClient
from PIL import Image
from playwright.async_api import BrowserType, async_playwright
from test_protocol import completion, model_endpoint
from yutori import AsyncYutoriClient
from yutori.navigator import aplaywright_screenshot_to_data_url


@unittest.skipUnless(os.environ.get("NOTTE_YUTORI_LIVE") == "1", "Real Notte browser tests are opt-in")
class BrowserTests(unittest.IsolatedAsyncioTestCase):
    def journal(self, event, session_id):
        if path := os.environ.get("YUTORI_OWNERSHIP_JOURNAL"):
            try:
                with open(path, "a") as journal:
                    journal.write(json.dumps({"event": event, "session_id": session_id}) + "\n")
                    journal.flush()
                    os.fsync(journal.fileno())
            except OSError:
                print("Ownership journal unavailable")

    def closed(self, session_id):
        root = os.environ["NOTTE_API_URL"].rstrip("/")
        headers = {"Authorization": f"Bearer {os.environ['NOTTE_API_KEY']}"}
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            response = requests.get(f"{root}/sessions/{session_id}", headers=headers, timeout=5)
            self.assertEqual(response.status_code, 200, "Owned session lookup failed")
            if response.json()["status"] == "closed":
                self.journal("closed", session_id)
                return
            time.sleep(0.5)
        self.fail("Owned browser did not close")

    @contextmanager
    def owned(self):
        self.assertTrue(os.environ.get("NOTTE_API_KEY"), "Set the Notte test key")
        self.assertTrue(os.environ.get("NOTTE_API_URL"), "Choose the test API explicitly")
        client = NotteClient()
        start = client.sessions.start
        ids = []

        def tracked(*args, **kwargs):
            result = start(*args, **kwargs)
            ids.append(result.session_id)
            self.journal("allocated", result.session_id)
            return result

        with (
            patch.object(client.sessions, "start", side_effect=tracked),
            patch.object(demo, "NotteClient", return_value=client),
        ):
            try:
                yield client
            finally:
                self.assertEqual(len(ids), 1, "Expected one owned browser")
                closed = False
                try:
                    self.closed(ids[0])
                    closed = True
                finally:
                    if not closed:
                        response = requests.delete(
                            f"{os.environ['NOTTE_API_URL'].rstrip('/')}/sessions/{ids[0]}/stop",
                            headers={"Authorization": f"Bearer {os.environ['NOTTE_API_KEY']}"},
                            timeout=15,
                        )
                        self.assertTrue(response.ok, "Owned fallback stop failed")
                        self.closed(ids[0])

    async def test_disconnect_faults_preserve_native_provider_rejection_and_stop(self):
        for mode in ("reject", "timeout"):
            with self.subTest(mode=mode):
                closes = []
                connect = BrowserType.connect_over_cdp

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
                    self.owned(),
                    model_endpoint([{"error": {"message": "PRIVATE_PROVIDER_FIXTURE"}}], status=401) as (url, _),
                    patch.object(BrowserType, "connect_over_cdp", new=connected),
                ):
                    async with AsyncYutoriClient(
                        api_key="test-only",  # pragma: allowlist secret
                        base_url=url,
                    ) as client:
                        with self.assertRaisesRegex(
                            demo.BrowserTaskError, r"Yutori model request failed \(HTTP 401\)"
                        ) as caught:
                            await asyncio.wait_for(demo.run("Read the title", client=client), timeout=30)
                    self.assertEqual(closes, [True], "The native disconnect fault must run")
                    self.assertIsNone(caught.exception.__cause__)
                    self.assertTrue(caught.exception.__suppress_context__)

    async def test_repeated_native_start_cancellation_stops_late_owned_browser(self):
        with self.owned() as client:
            allocated, release = asyncio.Event(), asyncio.Event()
            loop = asyncio.get_running_loop()
            start = client.sessions.start

            def delayed(*args, **kwargs):
                response = start(*args, **kwargs)
                loop.call_soon_threadsafe(allocated.set)
                asyncio.run_coroutine_threadsafe(release.wait(), loop).result(timeout=30)
                return response

            async def enter():
                async with demo.owned_connection():
                    self.fail("Cancelled creation must not enter the browser task")

            with patch.object(client.sessions, "start", side_effect=delayed):
                task = asyncio.create_task(enter())
                try:
                    await asyncio.wait_for(allocated.wait(), timeout=30)
                    task.cancel()
                    await asyncio.sleep(0)
                    task.cancel()
                finally:
                    release.set()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
                self.assertTrue(task.cancelled(), "The caller's cancellation must propagate")

    async def test_original_loop_with_native_protocol_fixture(self):
        with (
            self.owned(),
            model_endpoint([completion("goto_url", {"url": "https://example.com/?notte=yutori"}), completion()]) as (
                url,
                requests,
            ),
        ):
            async with AsyncYutoriClient(api_key="test-only", base_url=url) as client:  # pragma: allowlist secret
                result = await demo.run("Read the page title", client=client)
            self.assertEqual(result["answer"], "Example Domain")
            self.assertEqual(len(requests), 2)
            messages = requests[1]["payload"]["messages"]
            self.assertTrue(
                any(
                    message.get("role") == "tool" and message.get("content") == "Action completed"
                    for message in messages
                )
            )
            images = [
                part["image_url"]["url"]
                for message in messages
                if isinstance(message.get("content"), list)
                for part in message["content"]
                if part.get("type") == "image_url"
            ]
            self.assertEqual(len(images), 2)
            self.assertTrue(all(image.startswith("data:image/webp;base64,") for image in images))

    async def test_genuine_browser_navigation_failure_stops_session(self):
        with (
            self.owned(),
            model_endpoint([completion("goto_url", {"url": "https://notte-yutori-test.invalid"})]) as (url, _),
        ):
            async with AsyncYutoriClient(api_key="test-only", base_url=url) as client:  # pragma: allowlist secret
                with self.assertRaisesRegex(demo.BrowserTaskError, "Yutori browser action failed: goto_url"):
                    await demo.run("Read the page title", client=client)

    async def test_provider_rejection_is_safe_and_stops_session(self):
        sentinel = "test-only-private-provider-detail"
        with self.owned(), model_endpoint([{"error": {"message": sentinel}}], status=401) as (url, _):
            async with AsyncYutoriClient(api_key="test-only", base_url=url) as client:  # pragma: allowlist secret
                with self.assertRaisesRegex(
                    demo.BrowserTaskError, r"Yutori model request failed \(HTTP 401\)"
                ) as caught:
                    await demo.run("Read the page title", client=client)
            self.assertNotIn(sentinel, str(caught.exception))
            self.assertTrue(caught.exception.__suppress_context__)

    async def test_step_limit_stops_owned_session(self):
        with self.owned(), model_endpoint([completion("goto_url", {"url": "https://example.com"})]) as (url, requests):
            async with AsyncYutoriClient(api_key="test-only", base_url=url) as client:  # pragma: allowlist secret
                with self.assertRaisesRegex(demo.BrowserTaskError, "Yutori step limit reached"):
                    await demo.run("Read the page title", client=client, max_steps=1)
            self.assertEqual(len(requests), 1)

    async def test_native_screenshot_coordinates_keyboard_and_scroll(self):
        with self.owned() as client:
            with client.Session(
                max_duration_minutes=3, proxies=False, viewport_width=1280, viewport_height=800
            ) as session:
                async with async_playwright() as playwright:
                    browser = await playwright.chromium.connect_over_cdp(session.cdp_url())
                    try:
                        page = await browser.contexts[0].new_page()
                        await page.goto("https://example.com")
                        await page.set_content(
                            '<input style="position:absolute;left:20px;top:20px;width:200px;height:30px" id="name">'
                            '<div style="height:3000px"></div>'
                        )
                        await demo.act(page, "left_click", {"coordinates": [80, 45]})
                        await demo.act(page, "type", {"text": "Notte"})
                        self.assertEqual(await page.locator("#name").input_value(), "Notte")
                        await demo.act(page, "key_press", {"key": "ctrl+a"})
                        await demo.act(page, "type", {"text": "Navigator"})
                        self.assertEqual(await page.locator("#name").input_value(), "Navigator")
                        await demo.act(page, "scroll", {"coordinates": [500, 500], "direction": "down", "amount": 3})
                        for _ in range(20):
                            if await page.evaluate("scrollY") > 0:
                                break
                            await asyncio.sleep(0.1)
                        self.assertGreater(await page.evaluate("scrollY"), 0)
                        image = await aplaywright_screenshot_to_data_url(page)
                        self.assertEqual(
                            Image.open(io.BytesIO(base64.b64decode(image.split(",", 1)[1]))).size, (1280, 800)
                        )
                        await demo.act(page, "goto_url", {"url": "https://example.com/?step=one"})
                        await demo.act(page, "goto_url", {"url": "https://example.com/?step=two"})
                        await demo.act(page, "go_back", {})
                        self.assertIn("step=one", page.url)
                        await demo.act(page, "go_forward", {})
                        self.assertIn("step=two", page.url)
                        await demo.act(page, "refresh", {})
                        self.assertEqual(await page.title(), "Example Domain")
                        await demo.act(page, "wait", {"duration": 0})
                    finally:
                        await browser.close()


if __name__ == "__main__":
    unittest.main()
