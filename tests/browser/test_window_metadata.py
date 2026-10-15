"""Metadata values, browser-call budget, and existing failure semantics."""

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from notte_browser.errors import BrowserExpiredError, EmptyPageContentError
from notte_browser.playwright_async_api import Error, Page
from notte_browser.session import NotteSession
from notte_browser.window import BrowserWindow
from notte_core.snapshot import ViewportData

import notte


@pytest_asyncio.fixture(loop_scope="function")
async def session() -> AsyncIterator[NotteSession]:
    async with notte.Session(headless=True, viewport_width=1280, viewport_height=720) as session:
        yield session


async def _legacy_viewport(page: Page) -> ViewportData:
    return ViewportData(
        scroll_x=int(await page.evaluate("window.scrollX")),
        scroll_y=int(await page.evaluate("window.scrollY")),
        viewport_width=int(await page.evaluate("window.innerWidth")),
        viewport_height=int(await page.evaluate("window.innerHeight")),
        total_width=int(await page.evaluate("document.documentElement.scrollWidth")),
        total_height=int(await page.evaluate("document.documentElement.scrollHeight")),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("other_tabs", [0, 3])
async def test_metadata_browser_call_budget(session: NotteSession, other_tabs: int) -> None:
    page = session.window.page
    await page.set_content("<title>Active</title><main>Content</main>")
    for index in range(other_tabs):
        tab = await page.context.new_page()
        await tab.set_content(f"<title>Other {index}</title>")

    with (
        patch.object(Page, "evaluate", autospec=True, side_effect=Page.evaluate) as evaluate,
        patch.object(Page, "title", autospec=True, side_effect=Page.title) as title,
    ):
        metadata = await session.window.snapshot_metadata()

    assert evaluate.call_count == 1
    assert title.call_count == other_tabs
    assert evaluate.call_args.args[0] is page
    assert [call.args[0] for call in title.call_args_list] == page.context.pages[1:]
    assert metadata.title == "Active"
    assert [tab.title for tab in metadata.tabs] == ["Active", *[f"Other {i}" for i in range(other_tabs)]]
    assert [tab.tab_id for tab in metadata.tabs] == list(range(other_tabs + 1))
    assert [tab.url for tab in metadata.tabs] == [tab.url for tab in page.context.pages]


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["blank", "bodyless", "scrolled", "frames", "fractional"])
async def test_metadata_matches_legacy_values(session: NotteSession, case: str) -> None:
    page = session.window.page
    if case != "blank":
        await page.set_content(
            "<title>Metadata &amp; title</title><main style='width:2400px;height:3000px'>Text</main>"
        )
    if case == "bodyless":
        await page.evaluate("document.body.remove()")
    elif case == "scrolled":
        await page.evaluate("window.scrollTo(123, 456)")
    elif case == "frames":
        await page.set_content(
            '<title>Main frame</title><iframe srcdoc="<title>Child frame</title><p>Child</p>"></iframe>'
        )
        assert len(page.frames) == 2
    elif case == "fractional":
        # Include a negative offset: int() truncates towards zero, unlike floor().
        await page.evaluate("""Object.defineProperties(window, {
            scrollX: {get: () => -12.75}, scrollY: {get: () => 45.75}
        })""")

    title = await page.title()
    viewport = await _legacy_viewport(page)
    metadata = await session.window.snapshot_metadata()
    assert metadata.title == title
    assert metadata.url == page.url
    assert metadata.viewport == viewport
    assert all(type(value) is int for value in metadata.viewport.model_dump().values())
    assert metadata.tabs[0].title == title
    if case == "fractional":
        assert (metadata.viewport.scroll_x, metadata.viewport.scroll_y) == (-12, 45)


@pytest.mark.asyncio
async def test_missing_document_element_keeps_error_and_snapshot_retries(session: NotteSession) -> None:
    page = session.window.page
    await page.evaluate("document.documentElement.remove()")
    with pytest.raises(Error, match="scrollWidth"):
        await session.window.snapshot_metadata()
    with patch.object(Page, "evaluate", autospec=True, side_effect=Page.evaluate) as evaluate:
        with pytest.raises(EmptyPageContentError):
            await session.window.snapshot(screenshot=False, skip_dom=True, retries=2)
    assert evaluate.call_count == 2


@pytest.mark.asyncio
async def test_metadata_navigation_error_retries_same_snapshot_options(session: NotteSession) -> None:
    page = session.window.page
    await page.set_content("<main>Before</main>")
    evaluate = Page.evaluate
    calls = 0

    async def navigating(page: Page, expression: str):
        nonlocal calls
        calls += 1
        if calls == 1:
            await page.goto("data:text/html,<title>After</title><main>After</main>")
            raise Error("Execution context was destroyed, most likely because of a navigation")
        return await evaluate(page, expression)

    with (
        patch.object(Page, "evaluate", new=navigating),
        patch.object(BrowserWindow, "screenshot", side_effect=AssertionError("unexpected screenshot")),
    ):
        snapshot = await session.window.snapshot(screenshot=False, skip_dom=True, selector="main", retries=2)
    assert calls == 2
    assert snapshot.metadata.title == "After"
    assert snapshot.html_content == "After"
    assert not snapshot.interaction_nodes()
    assert snapshot.screenshot is None


@pytest.mark.asyncio
async def test_closed_active_page_switches_to_remaining_tab(session: NotteSession) -> None:
    page = session.window.page
    await page.goto("data:text/html,<title>Closing</title>")
    remaining = await page.context.new_page()
    await remaining.set_content("<title>Remaining</title>")
    await page.close()
    metadata = await session.window.snapshot_metadata()
    assert session.window.page is remaining
    assert metadata.title == metadata.tabs[0].title == "Remaining"
    assert len(metadata.tabs) == 1


@pytest.mark.asyncio
async def test_closed_last_page_keeps_errors(session: NotteSession) -> None:
    await session.window.page.close()
    with pytest.raises(Error, match="closed"):
        await session.window.snapshot_metadata()
    with pytest.raises(BrowserExpiredError):
        await session.window.snapshot(screenshot=False, skip_dom=True)
    tab = await session.window.tab_metadata()
    assert tab.title == tab.url == "about:blank"


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [Error("Target page has been closed"), TimeoutError()])
async def test_other_tab_title_failure_keeps_url_fallback(session: NotteSession, failure: Exception) -> None:
    page = session.window.page
    await page.set_content("<title>Active</title>")
    _ = await page.context.new_page()
    with patch.object(Page, "title", new=AsyncMock(side_effect=failure)):
        metadata = await session.window.snapshot_metadata()
    assert metadata.title == metadata.tabs[0].title == "Active"
    assert metadata.tabs[1].title == metadata.tabs[1].url == "about:blank"


@pytest.mark.asyncio
async def test_tab_title_timeout_remains_five_seconds(session: NotteSession) -> None:
    async def timeout(awaitable, *, timeout):
        awaitable.close()
        assert timeout == 5.0
        raise TimeoutError

    with patch("notte_browser.window.asyncio.wait_for", new=timeout):
        tab = await session.window.tab_metadata()
    assert tab.title == tab.url == "about:blank"
