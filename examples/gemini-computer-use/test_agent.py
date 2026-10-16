import asyncio
import base64
import os
import secrets
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
                    await page.set_content(
                        "<button onclick=\"window.open('about:blank','_blank').document.title='Popup'\">Open</button>"
                    )
                    destination = await agent.perform(page, "click", await point("button"))
                    self.assertIsNot(destination, page)
                    self.assertEqual(await destination.title(), "Popup")
                finally:
                    await browser.close()
        await closed(client, session.session_id)

    @unittest.skipUnless(os.getenv("NOTTE_GEMINI_LIVE") == "1", "Opt-in cloud browser test")
    async def test_delayed_popup_replans_stale_action(self):
        client, ids = NotteClient(), []
        original = client.sessions.start

        def start(**kwargs):
            result = original(**kwargs)
            ids.append(result.session_id)
            return result

        class Provider:
            calls = 0
            state = None

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_):
                return False

            @property
            def interactions(self):
                return self

            async def create(provider, **request):
                provider.calls += 1
                number = provider.calls
                if number == 2:
                    await asyncio.sleep(3)
                if number == 3:
                    provider.state = request["input"][0]["result"]
                step = (
                    SimpleNamespace(
                        type="function_call", id=f"call-{number}", name="click", arguments={"x": 50, "y": 50}
                    )
                    if number == 1
                    else SimpleNamespace(
                        type="function_call", id=f"call-{number}", name="type", arguments={"text": "stale"}
                    )
                    if number == 2
                    else SimpleNamespace(type="model_output", content=[SimpleNamespace(type="text", text="Done")])
                )
                return SimpleNamespace(id=f"interaction-{number}", status="completed", steps=[step])

        provider = Provider()
        html = """<button style="position:absolute;left:20px;top:20px;width:100px;height:50px" onclick="setTimeout(()=>{const p=window.open('about:blank');p.document.write('<title>Popup</title><input autofocus oninput=&quot;document.title=String.fromCharCode(83,116,97,108,101)&quot;>');p.document.close()},2500)">Open</button>"""
        try:
            with (
                patch.object(client.sessions, "start", side_effect=start),
                patch.object(agent, "NotteClient", return_value=client),
                patch.object(agent.genai, "Client", return_value=SimpleNamespace(aio=provider)),
                patch.dict(
                    os.environ,
                    {"GEMINI_API_KEY": "integration-test-not-a-real-key"},  # pragma: allowlist secret
                ),  # pragma: allowlist secret
            ):
                result = await agent.run(
                    "Open the new tab", "data:text/html;base64," + base64.b64encode(html.encode()).decode()
                )
            self.assertEqual(provider.calls, 3)
            self.assertIn("not executed", provider.state[0]["text"])
            self.assertTrue(provider.state[1]["data"])
            self.assertEqual(result["title"], "Popup")
            self.assertEqual(result["actions"], 1)
            self.assertEqual(ids, [result["session_id"]])
        finally:
            for session_id in ids:
                await closed(client, session_id)

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
            calls = 0

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_):
                return False

            @property
            def interactions(self):
                return self

            async def create(self, **_):
                self.calls += 1
                raise RuntimeError("Injected provider failure")

        provider = ProviderFailure()
        with (
            patch.object(client.sessions, "start", side_effect=start),
            patch.object(agent, "NotteClient", return_value=client),
            patch.object(agent.genai, "Client", return_value=SimpleNamespace(aio=provider)),
            patch.dict(os.environ, {"GEMINI_API_KEY": "integration-test-not-a-real-key"}),  # pragma: allowlist secret
        ):
            with self.assertRaisesRegex(RuntimeError, "^Gemini computer task failed$"):
                await agent.run("Read the page title")
        self.assertEqual(provider.calls, 1)
        self.assertEqual(len(ids), 1)
        await closed(client, ids[0])

    @unittest.skipUnless(os.getenv("NOTTE_GEMINI_MODEL_LIVE") == "1", "Opt-in actual Gemini model test")
    async def test_model_drives_browser(self):
        self.assertTrue(os.getenv("GEMINI_API_KEY"))
        self.assertTrue(os.getenv("NOTTE_API_URL"))
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
                nonce = secrets.token_hex(4).upper()
                html = f"""<title>Visual check</title><h1>Code: {nonce}</h1><label>Code<input></label><button onclick="document.title='Saved '+document.querySelector('input').value">Save</button>"""
                result = await agent.run(
                    "Read the code shown on the page. Enter it in the Code field, then click Save.",
                    "data:text/html;base64," + base64.b64encode(html.encode()).decode(),
                )
            self.assertEqual(result["title"], f"Saved {nonce}")
            self.assertGreater(result["actions"], 0)
            self.assertEqual(ids, [result["session_id"]])
        finally:
            for session_id in ids:
                await closed(client, session_id)
                print(f"Verified closed model session {session_id}")


if __name__ == "__main__":
    unittest.main()
