import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import demo
import httpx
from computer import NotteComputer, pixel
from fixture import Wire, response
from tzafon import AsyncLightcone


class Keyboard:
    def __init__(self):
        self.events = []

    async def press(self, key):
        self.events.append(("press", key))

    async def insert_text(self, text):
        self.events.append(("type", text))


class Page:
    viewport_size = {"width": 1024, "height": 768}

    def __init__(self):
        self.keyboard = Keyboard()
        self.mouse = self
        self.events = []

    async def screenshot(self, **kwargs):
        return b"fixture-png"

    async def click(self, x, y):
        self.events.append((x, y))


async def approve(action):
    return True


class ComputerContract(unittest.IsolatedAsyncioTestCase):
    async def test_native_wire_replays_history_without_persistence(self):
        wire, page = Wire(), Page()
        async with httpx.AsyncClient(transport=httpx.MockTransport(wire)) as http:
            async with AsyncLightcone(
                api_key="fixture-provider-key",  # pragma: allowlist secret
                base_url="https://lightcone.invalid",
                http_client=http,
                max_retries=0,  # pragma: allowlist secret
            ) as provider:
                await NotteComputer(page, approve).run(provider, "fixture task")
        self.assertEqual(page.events, [(163, 199)])
        self.assertEqual(page.keyboard.events, [("type", "orbit-fixture"), ("press", "Enter")])
        self.assertEqual(
            [item["type"] for item in wire.requests[1]["input"][1:]], ["computer_call", "computer_call_output"]
        )
        self.assertEqual(wire.requests[1]["input"][-1]["call_id"], "call_fixture_1")

    async def test_eighth_action_can_complete_but_ninth_is_refused(self):
        for complete in [True, False]:
            wire, page = Wire("limit"), Page()

            def handle(request):
                result = wire(request)
                return httpx.Response(200, json=response(None)) if complete and len(wire.requests) == 9 else result

            async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
                async with AsyncLightcone(
                    api_key="fixture-provider-key",  # pragma: allowlist secret
                    base_url="https://lightcone.invalid",
                    http_client=http,
                    max_retries=0,
                ) as provider:
                    computer = NotteComputer(page, approve)
                    if complete:
                        await computer.run(provider, "fixture")
                    else:
                        with self.assertRaisesRegex(RuntimeError, "limit"):
                            await computer.run(provider, "fixture")
                    self.assertEqual(len(computer.actions), 8)
                    self.assertEqual(len(wire.requests), 9)

    async def test_safety_and_denied_approval_have_no_effects(self):
        async def deny(action):
            return False

        for safety, approval in [(True, approve), (False, deny)]:
            page = Page()
            with self.assertRaises(PermissionError):
                await NotteComputer(page, approval).handle(
                    response({"type": "click", "x": 160, "y": 260, "button": "left"}, safety=safety)["output"][0]
                )
            self.assertEqual(page.events, [])

    async def test_cancelled_approval_never_acts(self):
        async def pending(action):
            await asyncio.Event().wait()
            return True

        page = Page()
        with self.assertRaises(TimeoutError):
            async with asyncio.timeout(0.02):
                await NotteComputer(page, pending).handle(
                    response({"type": "click", "x": 160, "y": 260, "button": "left"})["output"][0]
                )
        self.assertEqual(page.events, [])

    async def test_invalid_point_and_type_text_never_clicks_or_types(self):
        for text in [None, 7, [], "x" * 1001]:
            with self.subTest(text_type=type(text).__name__):
                page = Page()
                computer = NotteComputer(page, approve)
                with self.assertRaises(ValueError):
                    await computer.handle(
                        response({"type": "point_and_type", "x": 160, "y": 260, "text": text})["output"][0]
                    )
                self.assertEqual(page.events, [])
                self.assertEqual(page.keyboard.events, [])
                self.assertEqual(computer.actions, [])

    async def test_cleanup_failure_retains_the_created_session_id(self):
        class Session:
            session_id = "00000000-0000-4000-8000-000000000001"

            def __enter__(self):
                return self

            def __exit__(self, *args):
                raise RuntimeError("PRIVATE_FIXTURE_BODY")

            def cdp_url(self):
                return "wss://browser.invalid"

        class Client:
            def Session(self, **kwargs):
                return Session()

        browser = SimpleNamespace(contexts=[SimpleNamespace(pages=[Page()])], close=AsyncMock())
        driver = SimpleNamespace(chromium=SimpleNamespace(connect_over_cdp=AsyncMock(return_value=browser)))
        playwright = AsyncMock()
        playwright.__aenter__.return_value = driver
        with (
            patch.object(demo, "NotteClient", Client),
            patch.object(demo, "async_playwright", return_value=playwright),
            patch.object(demo, "_run_form", AsyncMock(return_value={"output": "Accepted"})),
        ):
            with self.assertRaisesRegex(
                RuntimeError, r"browser cleanup.*session 00000000-0000-4000-8000-000000000001"
            ) as caught:
                await demo.run_demo()
        self.assertNotIn("PRIVATE_FIXTURE_BODY", str(caught.exception))

    def test_coordinate_grid_boundaries(self):
        self.assertEqual((pixel(0, 1024), pixel(500, 1024), pixel(999, 1024)), (0, 512, 1022))
        for bad in [-1, 1000, float("nan"), float("inf"), True, "500"]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                pixel(bad, 1024)


if __name__ == "__main__":
    unittest.main()
