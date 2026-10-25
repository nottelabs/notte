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

# An inline script waits for the stylesheet before it, so the parser stops at the script until the CSS arrives.
STALL = '<link rel="stylesheet" href="https://fonts.test/style.css"><script>window.ready = true;</script>'
CONTENT = "<h1>Company</h1><p>Founded in 2025</p>"
HEAD_STALL = f"<html><head><title>Stalled page</title>{STALL}</head><body>{CONTENT}</body></html>"
BODY_STALL = f"<html><head><title>Stalled page</title></head><body>{STALL}{CONTENT}</body></html>"
# A tracking pixel in <noscript> is not page content, although the snapshot parses it as an image.
PIXEL_STALL = (
    "<html><head><title>Stalled page</title></head>"
    f'<body><noscript><img src="https://pixel.test/p.gif"></noscript>{STALL}{CONTENT}</body></html>'
)
IFRAME_FIRST = (
    "<html><head><title>Stalled page</title></head>"
    f'<body><iframe src="https://frame.test/"></iframe>{STALL}{CONTENT}</body></html>'
)
FRAME = "<p>framed content</p>"
EMPTY_BODY = "<html><head><title>Empty page</title></head><body></body></html>"

FULL_PAGE = ScrapeParams(only_main_content=False)


@pytest_asyncio.fixture(loop_scope="function")
async def session() -> AsyncIterator[NotteSession]:
    async with notte.Session(headless=True) as session:
        yield session


async def _open_stalled_page(session: NotteSession, page: str = HEAD_STALL) -> asyncio.Event:
    """Open `page` with its stylesheet held back until the returned event is set."""
    stylesheet = asyncio.Event()

    async def serve(route: Route) -> None:
        if route.request.url == "https://example.test/":
            await route.fulfill(body=page, content_type="text/html")
        elif route.request.url == "https://frame.test/":
            await route.fulfill(body=FRAME, content_type="text/html")
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
@pytest.mark.parametrize("page", [HEAD_STALL, BODY_STALL, PIXEL_STALL], ids=["head", "body", "noscript-pixel"])
async def test_page_whose_parser_waits_is_empty_not_its_title(session: NotteSession, page: str) -> None:
    stylesheet = await _open_stalled_page(session, page)
    assert await session.window.page.evaluate("document.readyState") == "loading"

    with pytest.raises(EmptyPageContentError):
        _ = await _markdown(session)

    stylesheet.set()
    _ = await session.window.page.wait_for_load_state("domcontentloaded")
    markdown = await _markdown(session)
    assert "Founded in 2025" in markdown


@pytest.mark.asyncio
async def test_snapshot_taken_before_the_parser_caught_up_is_empty(session: NotteSession) -> None:
    stylesheet = await _open_stalled_page(session)
    snapshot = await session.window.snapshot(skip_dom=True, screenshot=False)

    stylesheet.set()
    _ = await session.window.page.wait_for_load_state("domcontentloaded")

    with pytest.raises(EmptyPageContentError):
        _ = await page_markdown(session.window, snapshot, FULL_PAGE)


@pytest.mark.asyncio
async def test_iframe_parsed_before_the_stall_is_scraped(session: NotteSession) -> None:
    stylesheet = await _open_stalled_page(session, IFRAME_FIRST)
    try:
        frame = session.window.page.frame(url="https://frame.test/")
        for _ in range(50):
            if frame is not None:
                break
            await asyncio.sleep(0.1)
            frame = session.window.page.frame(url="https://frame.test/")
        assert frame is not None
        await frame.wait_for_load_state("domcontentloaded")

        markdown = await _markdown(session)
        assert "framed content" in markdown
    finally:
        stylesheet.set()


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
