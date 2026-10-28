"""Exercise stateless native computer calls without a browser or paid provider."""

import json
import unittest
from unittest.mock import AsyncMock, MagicMock

import httpx
from notte_computer import NotteComputer
from openai import AsyncOpenAI
from playwright.async_api import Page


class ProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_every_turn_replays_reasoning_actions_and_screenshots(self):
        payloads = []

        def respond(request):
            self.assertEqual(request.headers["Authorization"], "Bearer fixture-router-key")
            payloads.append(json.loads(request.content))
            turn = len(payloads)
            output = []
            if turn == 1:
                output.append({"id": "rs_1", "type": "reasoning", "summary": [], "encrypted_content": "opaque"})
            if turn <= 2:
                output.append(
                    {
                        "id": f"cu_{turn}",
                        "type": "computer_call",
                        "call_id": f"call_{turn}",
                        "status": "completed",
                        "actions": [{"type": "screenshot"}],
                        "pending_safety_checks": [],
                    }
                )
            return httpx.Response(
                200,
                json={
                    "id": f"resp_{turn}",
                    "object": "response",
                    "created_at": 0,
                    "model": "openai/gpt-6.1-sol",
                    "status": "completed",
                    "output": output,
                },
            )

        page = MagicMock(spec=Page)
        page.viewport_size = {"width": 1024, "height": 768}
        page.screenshot = AsyncMock(return_value=b"fixture-png")
        computer = NotteComputer(page, confirm=AsyncMock(return_value=True))
        async with AsyncOpenAI(
            api_key="fixture-router-key",  # pragma: allowlist secret
            base_url="https://router.invalid/v1",
            max_retries=0,
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)),
        ) as provider:
            await computer.run(provider, "Read the screen")

        self.assertEqual(len(payloads), 3)
        self.assertEqual(computer.actions, ["screenshot", "screenshot"])
        for payload in payloads:
            self.assertEqual(payload["model"], "openai/gpt-6.1-sol")
            self.assertEqual(payload["tools"], [{"type": "computer"}])
            self.assertFalse(payload["store"])
            self.assertEqual(payload["include"], ["reasoning.encrypted_content"])
            self.assertEqual(payload["provider"], {"allow_fallbacks": False})
            self.assertNotIn("previous_response_id", payload)
        self.assertEqual(
            [item.get("type", item.get("role")) for item in payloads[2]["input"]],
            [
                "user",
                "reasoning",
                "computer_call",
                "computer_call_output",
                "computer_call",
                "computer_call_output",
            ],
        )
        self.assertEqual(payloads[2]["input"][1]["encrypted_content"], "opaque")
        self.assertEqual(payloads[2]["input"][:4], payloads[1]["input"])
        for index, turn in ((3, 1), (5, 2)):
            screenshot = payloads[2]["input"][index]
            self.assertEqual(screenshot["call_id"], f"call_{turn}")
            self.assertEqual(
                screenshot["output"],
                {
                    "type": "computer_screenshot",
                    "image_url": "data:image/png;base64,Zml4dHVyZS1wbmc=",
                    "detail": "original",
                },
            )
