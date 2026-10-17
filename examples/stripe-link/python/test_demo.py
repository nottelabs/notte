import copy
import json
import unittest
from pathlib import Path
from typing import cast

import httpx
from demo import fill_approved_test_card
from link import AsyncClient
from link.errors import LinkAPIError
from playwright.async_api import Page

FIXTURE = json.loads((Path(__file__).parents[1] / "test-card.json").read_text())


class Field:
    def __init__(self) -> None:
        self.value = ""

    async def fill(self, value: str) -> None:
        self.value = value

    async def input_value(self) -> str:
        return self.value


class Form:
    def __init__(self) -> None:
        self.fields: dict[str, Field] = {}

    def get_by_label(self, label: str, *, exact: bool) -> Field:
        assert exact
        return self.fields.setdefault(label, Field())


class LinkContract(unittest.IsolatedAsyncioTestCase):
    async def fill(self, data: dict, *, status: int = 200) -> Form:
        form = Form()

        def handle(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.method, "GET")
            self.assertTrue(request.url.path.endswith("/spend_requests/lsrq_notte_fixture"))
            self.assertEqual(request.url.params.get("include"), "card")
            self.assertEqual(request.headers["authorization"], "Bearer test-link-token")
            return httpx.Response(status, json=data)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as transport:
            async with AsyncClient(access_token="test-link-token", http_client=transport) as wallet:
                await fill_approved_test_card(cast(Page, form), wallet, FIXTURE["id"])
        return form

    async def test_native_sdk_requests_card_expansion_and_fills_fields(self) -> None:
        form = await self.fill(FIXTURE)
        self.assertEqual(set(form.fields), {"Card number", "Expiry", "CVC"})
        self.assertEqual(form.fields["Expiry"].value, "12/2030")
        self.assertEqual(form.fields["Card number"].value, FIXTURE["card"]["number"])

    async def test_unapproved_and_unknown_statuses_cannot_fill(self) -> None:
        for status in ["created", "pending_approval", "denied", "expired", "submitted", "future_status"]:
            with self.subTest(status=status):
                data = copy.deepcopy(FIXTURE)
                data["status"] = status
                with self.assertRaisesRegex(RuntimeError, "needs approval"):
                    await self.fill(data)

    async def test_missing_and_non_test_credentials_cannot_fill(self) -> None:
        for change in [None, {"number": "4242424242424242"}, {"cvc": None}]:
            with self.subTest(change=change):
                data = copy.deepcopy(FIXTURE)
                if change is None:
                    data.pop("card")
                else:
                    data["card"].update(change)
                with self.assertRaises(RuntimeError):
                    await self.fill(data)

    async def test_native_sdk_retains_authoritative_http_rejection(self) -> None:
        with self.assertRaises(LinkAPIError) as caught:
            await self.fill({"error": {"message": "fixture rejection"}}, status=401)
        self.assertEqual(caught.exception.status, 401)


if __name__ == "__main__":
    unittest.main()
