import asyncio
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from notte_browser.errors import EmptyPageContentError
from notte_browser.scrape import page_markdown
from notte_browser.session import NotteSession
from notte_core.types import ScrapeParams
from patchright.async_api import Route

import notte

# The inline script waits for the stylesheet before it, so the parser stops in <head> until the CSS arrives.
PAGE = (
    "<html><head><title>Stalled page</title>"
    '<link rel="stylesheet" href="https://fonts.test/style.css">'
    "<script>window.ready = true;</script>"
    "</head><body><h1>Company</h1><p>Founded in 2025</p></body></html>"
)
EMPTY_BODY = "<html><head><title>Empty page</title></head><body></body></html>"

FULL_PAGE = ScrapeParams(only_main_content=False)


@pytest_asyncio.fixture(loop_scope="function")
async def session() -> AsyncIterator[NotteSession]:
    async with notte.Session(headless=True) as session:
        yield session


async def _open_stalled_page(session: NotteSession) -> asyncio.Event:
    """Open PAGE with its stylesheet held back until the returned event is set."""
    stylesheet = asyncio.Event()

    async def serve(route: Route) -> None:
        if route.request.url == "https://example.test/":
            await route.fulfill(body=PAGE, content_type="text/html")
        else:
            await stylesheet.wait()
            await route.fulfill(body="h1 { color: red; }", content_type="text/css")

    await session.window.page.route("**/*", serve)
    _ = await session.window.page.goto("https://example.test/", wait_until="commit")
    return stylesheet


async def _markdown(session: NotteSession, params: ScrapeParams = FULL_PAGE) -> str:
    snapshot = await session.window.snapshot(selector=params.selector, skip_dom=True, screenshot=False)
    return await page_markdown(session.window, snapshot, params)


@pytest.mark.asyncio
async def test_page_whose_parser_waits_in_head_is_empty_not_its_title(session: NotteSession) -> None:
    stylesheet = await _open_stalled_page(session)
    assert await session.window.page.evaluate("document.readyState") == "loading"

    with pytest.raises(EmptyPageContentError):
        _ = await _markdown(session)

    stylesheet.set()
    _ = await session.window.page.wait_for_load_state("domcontentloaded")
    markdown = await _markdown(session)
    assert "Founded in 2025" in markdown


@pytest.mark.asyncio
async def test_selector_scrape_of_a_loading_page_is_left_alone(session: NotteSession) -> None:
    stylesheet = await _open_stalled_page(session)
    try:
        markdown = await _markdown(session, ScrapeParams(only_main_content=False, selector="head"))
        assert "Stalled page" in markdown
    finally:
        stylesheet.set()


@pytest.mark.asyncio
async def test_loaded_page_with_an_empty_body_still_scrapes(session: NotteSession) -> None:
    async def serve(route: Route) -> None:
        await route.fulfill(body=EMPTY_BODY, content_type="text/html")

    await session.window.page.route("**/*", serve)
    _ = await session.window.page.goto("https://example.test/", wait_until="load")

    assert (await _markdown(session)).strip() == "Empty page"
