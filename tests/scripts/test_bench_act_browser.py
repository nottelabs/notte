"""Local benchmark fixtures obey their rules for keyboard input and overlapping searches."""

import threading
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import pytest
from notte_browser.session import NotteSession

from scripts.bench_act import bench


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
