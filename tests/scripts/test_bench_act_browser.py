"""Local benchmark fixtures obey their rules for keyboard input and overlapping searches."""

import json
import threading
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import pytest
from notte_browser.session import NotteSession

from scripts.bench_act import bench, registry


@pytest.fixture(scope="module")
def fixture_url() -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=str(bench.FIXTURES)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.mark.asyncio
@pytest.mark.parametrize("code", ["", "SAVE20"])
@pytest.mark.parametrize("submit", ["click", "enter"])
async def test_coupon_keyboard_and_button_submissions_match(fixture_url: str, code: str, submit: str) -> None:
    async with NotteSession(headless=True) as session:
        page = session.window.page
        _ = await page.goto(f"{fixture_url}/coupon.html")
        await page.locator("#coupon").fill(code)
        if submit == "enter":
            await page.locator("#coupon").press("Enter")
        else:
            await page.locator("#go").click()
        await page.wait_for_url("**/applied.html?*")
        query = parse_qs(urlsplit(page.url).query)
        assert query == ({"code": [code]} if code else {"skipped": ["1"]})
        assert ("$96.00" if code else "$120.00") in await page.inner_text("body")


@pytest.mark.asyncio
async def test_old_search_response_cannot_render_during_new_query_debounce(fixture_url: str) -> None:
    async with NotteSession(headless=True) as session:
        page = session.window.page
        now = datetime(2026, 10, 26, tzinfo=timezone.utc)
        await page.clock.install(time=now)
        await page.clock.pause_at(now + timedelta(seconds=1))
        _ = await page.goto(f"{fixture_url}/cov2/debounce.html")
        await page.locator("#q").fill("lis")
        await page.clock.fast_forward(600)
        await page.locator("#q").fill("london")
        await page.clock.fast_forward(500)
        assert await page.locator("#results li").count() == 0
        await page.clock.fast_forward(100)
        await page.clock.fast_forward(500)
        assert await page.inner_text("#results") == "London on a budget"


@pytest.mark.asyncio
@pytest.mark.parametrize("back_from", [2, 3])
@pytest.mark.parametrize("reviewed_speed", ["standard", "express"])
async def test_wizard_records_the_step_and_delivery_speed_that_back_left(
    fixture_url: str, back_from: int, reviewed_speed: str
) -> None:
    task = registry.discover().tasks["f3-wizard"]
    async with NotteSession(headless=True) as session:
        page = session.window.page
        _ = await page.goto(f"{fixture_url}/cov3/wizard.html")
        await page.locator("#name").fill("Ana Ruiz")
        await page.locator("#email").fill("ana.ruiz@example.com")
        await page.locator("#next").click()
        if back_from == 2:
            await page.locator("#back").click()
            await page.locator("#next").click()
        await page.locator("#zip").fill("28013")
        await page.locator("#date").fill("05122026")
        await page.locator(f'[name="speed"][value="{reviewed_speed}"]').check()
        if back_from == 3:
            await page.locator("#next").click()
            await page.locator("#back").click()
        await page.locator('[name="speed"][value="express"]').check()
        await page.locator("#next").click()
        await page.locator("#place").click()
        await page.wait_for_url("**/wizard-done.html?*")
        run = {"steps": [{"status": "executed", "operation": "CLICK", "target_label": "Back"}]}
        assert task.check({"url": page.url}, run) == (back_from == 3 and reviewed_speed == "standard")
        assert parse_qs(urlsplit(page.url).query).get("back_from") == (["3"] if back_from == 3 else None)
        assert parse_qs(urlsplit(page.url).query).get("reviewed_speed") == (
            [reviewed_speed] if back_from == 3 else None
        )


@pytest.mark.asyncio
async def test_wizard_enter_cannot_submit_before_review(fixture_url: str) -> None:
    async with NotteSession(headless=True) as session:
        page = session.window.page
        _ = await page.goto(f"{fixture_url}/cov3/wizard.html")
        await page.locator("#name").fill("Ana Ruiz")
        await page.locator("#email").fill("ana.ruiz@example.com")
        await page.locator("#email").press("Enter")
        assert await page.inner_text("#progress") == "Step 1 of 3: Your details"
        await page.locator("#next").click()
        await page.locator("#zip").fill("28013")
        await page.locator("#date").fill("05122026")
        await page.locator("#date").press("Enter")
        assert urlsplit(page.url).path == "/cov3/wizard.html"
        assert await page.inner_text("#progress") == "Step 2 of 3: Delivery"
        await page.locator("#next").click()
        await page.locator("#place").press("Enter")
        await page.wait_for_url("**/wizard-done.html?*")


@pytest.mark.asyncio
@pytest.mark.parametrize("try_taken", [False, True])
async def test_workspace_carries_completed_name_checks_through_submission(fixture_url: str, try_taken: bool) -> None:
    task = registry.discover().tasks["f3-validsubmit"]
    async with NotteSession(headless=True) as session:
        page = session.window.page
        _ = await page.goto(f"{fixture_url}/cov3/validsubmit.html")
        if try_taken:
            await page.locator("#ws").fill("Acme")
            await page.wait_for_function("document.getElementById('ws-status').textContent.includes('already taken')")
            assert not await page.locator("#create").is_enabled()
        await page.locator("#ws").fill("Acme Studio")
        await page.locator("#pw").fill("Blue-Kite-2026")
        await page.locator("#create").click()
        await page.wait_for_url("**/workspace-done.html?*")
        checked = json.loads(parse_qs(urlsplit(page.url).query)["checked"][0])
        assert checked == (["acme", "acme studio"] if try_taken else ["acme studio"])
        assert task.check({"url": page.url}, {}) is try_taken
