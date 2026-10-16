import asyncio
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import agent
from notte_sdk import NotteClient
from playwright.async_api import async_playwright


async def closed(client, session_id):
    for _ in range(30):
        if (await asyncio.to_thread(client.sessions.status, session_id)).status == "closed":
            return
        await asyncio.sleep(0.5)
    raise AssertionError("The browser session did not close")


class ComputerUseTests(unittest.IsolatedAsyncioTestCase):
    async def test_safety_decisions_prevent_browser_access(self):
        for decision in ["require_confirmation", "blocked", "unknown", False]:
            with self.subTest(decision=decision), self.assertRaises(PermissionError):
                await agent.execute(None, "click", {"safety_decision": {"decision": decision}})

    @unittest.skipUnless(os.getenv("NOTTE_GEMINI_LIVE") == "1", "Opt-in cloud browser test")
    async def test_form_actions_and_confirmation(self):
        self.assertTrue(os.getenv("NOTTE_API_URL"), "Choose the browser API explicitly")
        client = NotteClient()
        with client.Session(max_duration_minutes=3) as session:
            async with async_playwright() as driver:
                browser = await driver.chromium.connect_over_cdp(session.cdp_url())
                try:
                    page = await browser.contexts[0].new_page()
                    await page.set_viewport_size({"width": 1440, "height": 900})
                    await page.set_content(
                        "<input aria-label=\"Name\"><button onclick=\"document.title='Saved '+document.querySelector('input').value\">Save</button>"
                    )

                    async def point(selector):
                        box = await page.locator(selector).bounding_box()
                        return {
                            "x": int((box["x"] + box["width"] / 2) * 1000 / 1440),
                            "y": int((box["y"] + box["height"] / 2) * 1000 / 900),
                        }

                    await agent.execute(page, "click", await point("input"))
                    await agent.execute(page, "type", {"text": "Replace me"})
                    await agent.execute(page, "hotkey", {"keys": ["CTRL", "A"]})
                    await agent.execute(page, "type", {"text": "Ada"})
                    self.assertEqual(await page.locator("input").input_value(), "Ada")
                    save = await point("button")
                    with self.assertRaises(PermissionError):
                        await agent.execute(
                            page, "click", {**save, "safety_decision": {"decision": "require_confirmation"}}
                        )
                    self.assertEqual(await page.title(), "")
                    await agent.execute(page, "click", save)
                    self.assertEqual(await page.title(), "Saved Ada")
                    with self.assertRaises(ValueError):
                        await agent.execute(page, "click", {"x": 1000, "y": 2})
                    with self.assertRaises(ValueError):
                        await agent.execute(page, "shell", {})
                finally:
                    await browser.close()
        await closed(client, session.session_id)

    @unittest.skipUnless(os.getenv("NOTTE_GEMINI_LIVE") == "1", "Opt-in cloud browser test")
    async def test_provider_failure_closes_browser(self):
        self.assertTrue(os.getenv("NOTTE_API_URL"))
        client, ids = NotteClient(), []
        original = client.sessions.start

        def start(**kwargs):
            result = original(**kwargs)
            ids.append(result.session_id)
            return result

        class ProviderFailure:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *_):
                return False

            @property
            def interactions(self):
                return self

            async def create(self, **_):
                raise RuntimeError("Injected provider failure")

        with (
            patch.object(client.sessions, "start", side_effect=start),
            patch.object(agent, "NotteClient", return_value=client),
            patch.object(agent.genai, "Client", return_value=SimpleNamespace(aio=ProviderFailure())),
            patch.dict(os.environ, {"GEMINI_API_KEY": "integration-test-not-a-real-key"}),  # pragma: allowlist secret
        ):
            with self.assertRaisesRegex(RuntimeError, "^Gemini computer task failed$"):
                await agent.run("Read the page title")
        self.assertEqual(len(ids), 1)
        await closed(client, ids[0])

    @unittest.skipUnless(os.getenv("NOTTE_GEMINI_MODEL_LIVE") == "1", "Opt-in actual Gemini model test")
    async def test_model_drives_browser(self):
        self.assertTrue(os.getenv("GEMINI_API_KEY"))
        self.assertTrue(os.getenv("NOTTE_API_URL"))
        result = await agent.run("Go to https://example.com and read its page title.")
        self.assertEqual(result["title"], "Example Domain")
        self.assertGreater(result["actions"], 0)
        await closed(NotteClient(), result["session_id"])


if __name__ == "__main__":
    unittest.main()
