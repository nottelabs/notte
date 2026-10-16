import asyncio
import base64
import io
import os
import time
import unittest
from contextlib import contextmanager
from unittest.mock import patch

import main as demo
from notte_sdk import NotteClient
from PIL import Image
from playwright.async_api import async_playwright
from test_protocol import completion, model_endpoint
from yutori import AsyncYutoriClient
from yutori.navigator import aplaywright_screenshot_to_data_url


@unittest.skipUnless(os.environ.get("NOTTE_YUTORI_LIVE") == "1", "Real Notte browser tests are opt-in")
class BrowserTests(unittest.IsolatedAsyncioTestCase):
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
            return result

        with (
            patch.object(client.sessions, "start", side_effect=tracked),
            patch.object(demo, "NotteClient", return_value=client),
        ):
            try:
                yield client
            finally:
                self.assertEqual(len(ids), 1, "Expected one owned browser")
                for _ in range(30):
                    status = client.sessions.status(session_id=ids[0])
                    if status.status == "closed":
                        break
                    time.sleep(0.5)
                self.assertEqual(status.status, "closed", "Owned browser did not close")

    async def test_original_loop_with_native_protocol_fixture(self):
        with (
            self.owned(),
            model_endpoint([completion("goto_url", {"url": "https://example.com/?notte=yutori"}), completion()]) as (
                url,
                requests,
            ),
        ):
            async with AsyncYutoriClient(api_key="test-only", base_url=url) as client:
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
            async with AsyncYutoriClient(api_key="test-only", base_url=url) as client:
                with self.assertRaisesRegex(demo.BrowserTaskError, "Yutori browser action failed: goto_url"):
                    await demo.run("Read the page title", client=client)

    async def test_provider_rejection_is_safe_and_stops_session(self):
        sentinel = "test-only-private-provider-detail"
        with self.owned(), model_endpoint([{"error": {"message": sentinel}}], status=401) as (url, _):
            async with AsyncYutoriClient(api_key="test-only", base_url=url) as client:
                with self.assertRaisesRegex(
                    demo.BrowserTaskError, r"Yutori model request failed \(HTTP 401\)"
                ) as caught:
                    await demo.run("Read the page title", client=client)
            self.assertNotIn(sentinel, str(caught.exception))
            self.assertTrue(caught.exception.__suppress_context__)

    async def test_step_limit_stops_owned_session(self):
        with self.owned(), model_endpoint([completion("goto_url", {"url": "https://example.com"})]) as (url, requests):
            async with AsyncYutoriClient(api_key="test-only", base_url=url) as client:
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
