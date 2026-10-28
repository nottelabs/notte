import tempfile

import pytest
from notte_sdk.client import AsyncNotteClient, NotteClient
from patchright.sync_api import Route, sync_playwright
from playwright.async_api import Route as AsyncRoute


def test_cdp_connection():
    client = NotteClient()
    with client.Session(proxies=False) as session:
        # get cdp url
        cdp_url = session.cdp_url()
        # connect using CDP
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(cdp_url)
            page = browser.contexts[0].pages[0]
            fixture_url = "https://cdp-fixture.notte.test/"

            def serve_fixture(route: Route) -> None:
                route.fulfill(
                    status=200,
                    content_type="text/html",
                    body="<!doctype html><title>CDP fixture</title><h1>Connected over CDP</h1>",
                )

            page.route(fixture_url, serve_fixture)
            response = page.goto(fixture_url)
            assert response is not None and response.status == 200
            assert page.url == fixture_url
            assert page.title() == "CDP fixture"
            assert page.locator("h1").inner_text() == "Connected over CDP"
            with tempfile.TemporaryDirectory() as tmp_dir:
                screenshot = page.screenshot(path=f"{tmp_dir}/screenshot.png")
            assert screenshot is not None


def test_session_page_leaves_native_dialogs_to_backend():
    client = NotteClient()
    with client.Session(proxies=False) as session:
        page = session.page
        _ = page.goto("https://example.com")
        _ = page.evaluate("window.onbeforeunload = () => 'leave?'")

        result = session.execute(type="goto", url="https://example.org", raise_on_failure=True)

        page.wait_for_url("https://example.org/**")
        assert result.success
        assert page.title() == "Example Domain"


@pytest.mark.asyncio
async def test_async_session_page_and_operations():
    async with AsyncNotteClient() as client, client.Session(proxies=False) as session:
        page = await session.page
        assert await session.page is page
        fixture_url = "https://cdp-fixture.notte.test/async"

        async def serve_fixture(route: AsyncRoute) -> None:
            await route.fulfill(
                status=200,
                content_type="text/html",
                body='<!doctype html><title>Async CDP fixture</title><a href="#new">new</a>',
            )

        await page.route(fixture_url, serve_fixture)
        response = await page.goto(fixture_url)
        assert response is not None and response.status == 200
        await page.get_by_role("link", name="new", exact=True).click()
        assert page.url == f"{fixture_url}#new"
        assert await page.title() == "Async CDP fixture"
        assert (await session.status()).status == "active"
        assert await page.screenshot()
