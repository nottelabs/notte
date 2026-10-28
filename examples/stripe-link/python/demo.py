import asyncio
import json
import os
import sys

from link import AsyncClient
from notte_sdk import AsyncNotteClient
from playwright.async_api import Page, async_playwright


class LinkFormError(RuntimeError):
    pass


def safe_failure(error: Exception, stage: str, session_id: str) -> LinkFormError:
    if isinstance(error, LinkFormError):
        return error
    status = getattr(error, "status", None)
    detail = f" HTTP {status}" if isinstance(status, int) and 100 <= status <= 599 else ""
    return LinkFormError(f"Link form failed: {stage} [{type(error).__name__}]{detail} (session {session_id})")


async def fill_approved_test_card(page: Page, wallet: AsyncClient, request_id: str) -> None:
    """Fill an approved Link test credential without submitting a payment."""
    request = await wallet.spend_requests.retrieve(request_id, include=["card"])
    if request is None or request.status != "approved" or request.card is None:
        raise RuntimeError("The Link spend request needs approval and a card credential")
    card = request.card
    # Link's published test credential. This example refuses real cards.
    if card.number != "4000009990001984" or not card.cvc:  # pragma: allowlist secret
        raise RuntimeError("Use an approved Link test-mode card request")
    fields = {"Card number": card.number, "Expiry": f"{card.exp_month:02d}/{card.exp_year}", "CVC": card.cvc}
    for label, value in fields.items():
        await page.get_by_label(label, exact=True).fill(value)
        if await page.get_by_label(label, exact=True).input_value() != value:
            raise RuntimeError("A test card field was not filled")


async def run_demo(wallet: AsyncClient | None = None) -> dict:
    for name in ["LINK_ACCESS_TOKEN", "LINK_SPEND_REQUEST_ID"]:
        if not os.environ.get(name):
            raise RuntimeError(f"Set {name}")
    client = AsyncNotteClient()
    session_id = "not-created"
    stage = "create browser"
    try:
        async with client, client.Session(max_duration_minutes=3) as session:
            session_id = session.session_id
            try:
                stage = "open test form"
                async with async_playwright() as driver:
                    browser = await driver.chromium.connect_over_cdp(await session.cdp_url())
                    try:
                        page = browser.contexts[0].pages[0]
                        await page.goto("about:blank")
                        await page.set_content(
                            '<label>Card number<input type="password" autocomplete="off"></label>'
                            '<label>Expiry<input autocomplete="off"></label>'
                            '<label>CVC<input type="password" autocomplete="off"></label>'
                        )
                        stage = "retrieve and fill approved test card"
                        async with wallet or AsyncClient(access_token=os.environ["LINK_ACCESS_TOKEN"]) as wallet:
                            await fill_approved_test_card(page, wallet, os.environ["LINK_SPEND_REQUEST_ID"])
                    finally:
                        failed = sys.exception() is not None
                        if not failed:
                            stage = "disconnect browser"
                        try:
                            await asyncio.wait_for(browser.close(), timeout=5)
                        except Exception:
                            if not failed:
                                raise RuntimeError("Browser disconnect failed") from None
            except Exception as error:
                raise safe_failure(error, stage, session_id) from None
        return {"filled": True, "session_id": session_id}
    except Exception as error:
        raise safe_failure(error, stage, session_id) from None


if __name__ == "__main__":
    try:
        with asyncio.Runner() as runner:
            print(json.dumps(runner.run(run_demo())))
    except Exception as error:
        print(str(error))
        raise SystemExit(1) from None
