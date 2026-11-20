"""A click on an element that stays hidden, covered or out of the viewport falls back to a script click at once, instead
of after four fifths of its timeout; a cover of a moment still gets the pointer click (`execution._pointer_click`)."""

import asyncio
import time
from collections.abc import AsyncIterator, Awaitable, Callable

import pytest
import pytest_asyncio
from notte_browser.execution import _CLICK_BLOCKED_MS, _CLICK_BLOCKED_REQUEST_S, _CLICK_FIRST_SLICE_MS
from notte_browser.session import NotteSession
from notte_core.actions import ClickAction
from patchright.async_api import Frame, Route

# the earliest a lasting cover is given up on (s), and well before the old fallback at four fifths of 15 s
EARLIEST_FALLBACK_S = (_CLICK_FIRST_SLICE_MS + _CLICK_BLOCKED_MS) / 1000
FALLBACK_BOUND_S = 8.0
# the cover's request runs this long (s)
REQUEST_S = 2.5

# the clicks are recorded in the DOM, which the page scripts and the test share; `trusted` tells a pointer click
# (true) from a script click (false)
BUTTON = """<button id="target" style="position: fixed; left: 10px; top: 10px"
  onclick="document.body.dataset.clicks = Number(document.body.dataset.clicks || 0) + 1;
           document.body.dataset.trusted = event.isTrusted">Apply</button>"""
COVER = '<div id="cover" style="position: fixed; inset: 0; background: white"></div>'


@pytest_asyncio.fixture(loop_scope="function")
async def session() -> AsyncIterator[NotteSession]:
    async with NotteSession(headless=True) as session:
        yield session


async def click(
    session: NotteSession, html: str | None, *, action: ClickAction | None = None, frame: Frame | None = None
) -> tuple[float, int, bool | None]:
    """Clicks `#target` on a page of `html` (None: the page as it is): how long the click took (s), how many clicks the
    button got and whether the last one was the pointer's, read from `frame` (the page's main frame by default)."""
    if html is not None:
        await session.window.page.set_content(html)
    start = time.monotonic()
    result = await session.aexecute(action or ClickAction(selector="#target"), raise_on_failure=False)
    elapsed = time.monotonic() - start
    assert result.success, result.message
    frame = frame or session.window.page.main_frame
    clicks: int = await frame.evaluate("Number(document.body.dataset.clicks || 0)")
    trusted: str | None = await frame.evaluate("document.body.dataset.trusted ?? null")
    return elapsed, clicks, None if trusted is None else trusted == "true"


def serve_json(after_s: float) -> Callable[[Route], Awaitable[None]]:
    """A route handler answering `{}` after `after_s`."""

    async def serve(route: Route) -> None:
        await asyncio.sleep(after_s)
        await route.fulfill(body="{}", content_type="application/json", headers={"Access-Control-Allow-Origin": "*"})

    return serve


@pytest.mark.asyncio
async def test_a_click_on_an_element_that_stays_covered_falls_back_at_once(session: NotteSession) -> None:
    elapsed, clicks, trusted = await click(session, BUTTON + COVER)

    assert (clicks, trusted) == (1, False)
    assert EARLIEST_FALLBACK_S <= elapsed < FALLBACK_BOUND_S


@pytest.mark.asyncio
async def test_a_click_on_an_element_that_stays_hidden_falls_back_at_once(session: NotteSession) -> None:
    elapsed, clicks, trusted = await click(session, BUTTON.replace("fixed;", "fixed; visibility: hidden;"))

    assert (clicks, trusted) == (1, False)
    assert EARLIEST_FALLBACK_S <= elapsed < FALLBACK_BOUND_S


@pytest.mark.asyncio
async def test_a_click_on_an_element_kept_out_of_the_viewport_falls_back_at_once(session: NotteSession) -> None:
    # a fixed element placed past the viewport (a drawer slid off-screen): scrolling cannot bring it into view
    elapsed, clicks, trusted = await click(session, BUTTON.replace("10px", "3000px"))

    assert (clicks, trusted) == (1, False)
    assert EARLIEST_FALLBACK_S <= elapsed < FALLBACK_BOUND_S


@pytest.mark.asyncio
async def test_a_click_the_page_handles_past_its_slice_is_sent_once(session: NotteSession) -> None:
    # the button's handler keeps the page busy for longer than the first slice: the deadline falls while the page
    # handles the click, and Playwright raises its timeout for a click it delivered. The next slice must not click again
    busy_ms = _CLICK_FIRST_SLICE_MS + 1000
    html = BUTTON.replace(
        'event.isTrusted">',
        f'event.isTrusted; const end = performance.now() + {busy_ms}; while (performance.now() < end) {{}}">',
    )
    elapsed, clicks, trusted = await click(session, html)

    assert (clicks, trusted) == (1, True)
    assert elapsed < FALLBACK_BOUND_S


@pytest.mark.asyncio
async def test_a_click_waits_for_a_cover_of_a_moment(session: NotteSession) -> None:
    # covered past the first slice, uncovered before a cover counts as lasting
    gone_ms = _CLICK_FIRST_SLICE_MS + _CLICK_BLOCKED_MS // 2
    html = BUTTON + COVER + f"<script>setTimeout(() => document.getElementById('cover').remove(), {gone_ms})</script>"
    elapsed, clicks, trusted = await click(session, html)

    assert (clicks, trusted) == (1, True)
    assert gone_ms / 1000 <= elapsed < EARLIEST_FALLBACK_S + 1


@pytest.mark.asyncio
async def test_a_click_waits_for_a_cover_that_moves(session: NotteSession) -> None:
    # the cover slides off the button over 2 s, longer than a lasting cover: it is not one while it moves
    html = (
        BUTTON
        + COVER.replace("background: white", "background: white; transition: transform 2s linear")
        + "<script>requestAnimationFrame(() => requestAnimationFrame(() =>"
        + " { document.getElementById('cover').style.transform = 'translateX(-100%)' }))</script>"
    )
    elapsed, clicks, trusted = await click(session, html)

    assert (clicks, trusted) == (1, True)
    assert 1.5 <= elapsed < FALLBACK_BOUND_S


@pytest.mark.asyncio
async def test_a_click_waits_for_a_cover_while_a_request_runs(session: NotteSession) -> None:
    # a spinner over the page until its data arrives: the pointer click lands once it does
    async def serve(route: Route) -> None:
        await asyncio.sleep(REQUEST_S)
        await route.fulfill(body="{}", content_type="application/json", headers={"Access-Control-Allow-Origin": "*"})

    await session.window.page.route("http://data.test/**", serve)
    html = (
        BUTTON
        + COVER
        + "<script>fetch('http://data.test/data').then(() => document.getElementById('cover').remove())</script>"
    )
    elapsed, clicks, trusted = await click(session, html)

    assert (clicks, trusted) == (1, True)
    assert REQUEST_S <= elapsed < FALLBACK_BOUND_S


@pytest.mark.asyncio
async def test_a_request_the_page_keeps_open_does_not_hold_the_fallback(session: NotteSession) -> None:
    # a beacon that never answers (analytics) is not what the cover waits for: the fallback comes once it is old
    never = asyncio.Event()

    async def serve(route: Route) -> None:
        await never.wait()
        await route.fulfill(body="{}", content_type="application/json", headers={"Access-Control-Allow-Origin": "*"})

    await session.window.page.route("http://data.test/**", serve)
    html = BUTTON + COVER + "<script>fetch('http://data.test/beacon')</script>"
    try:
        elapsed, clicks, trusted = await click(session, html)
    finally:
        never.set()

    assert (clicks, trusted) == (1, False)
    assert _CLICK_BLOCKED_REQUEST_S <= elapsed < FALLBACK_BOUND_S


@pytest.mark.asyncio
async def test_a_click_waits_for_a_cover_while_the_page_changes(session: NotteSession) -> None:
    # the page renders while covered (a list filling in), then uncovers: the pointer click lands
    gone_ms = int(EARLIEST_FALLBACK_S * 1000) + 800
    html = (
        BUTTON
        + COVER
        + f"""<ul id="list"></ul><script>
          const fill = setInterval(() => document.getElementById('list').append(document.createElement('li')), 100);
          setTimeout(() => {{ clearInterval(fill); document.getElementById('cover').remove() }}, {gone_ms});
        </script>"""
    )
    elapsed, clicks, trusted = await click(session, html)

    # the list grows every 100 ms: the page is never idle for the required window while the button is covered
    assert (clicks, trusted) == (1, True)
    assert gone_ms / 1000 <= elapsed < FALLBACK_BOUND_S


@pytest.mark.asyncio
async def test_a_click_waits_for_a_cover_while_a_label_counts(session: NotteSession) -> None:
    # a "please wait" screen whose one progress label ticks every 100 ms, then uncovers: the pointer click lands.
    # The settle tracker counts a node's text changes twice only (a clock is not an action's effect); the page is
    # busy all the same
    gone_ms = int(EARLIEST_FALLBACK_S * 1000) + 800
    html = (
        BUTTON
        + COVER.replace("</div>", '<span id="progress">0%</span></div>')
        + f"""<script>
          let pct = 0;
          const tick = setInterval(() => {{ document.getElementById('progress').textContent = ++pct + '%' }}, 100);
          setTimeout(() => {{ clearInterval(tick); document.getElementById('cover').remove() }}, {gone_ms});
        </script>"""
    )
    elapsed, clicks, trusted = await click(session, html)

    assert (clicks, trusted) == (1, True)
    assert gone_ms / 1000 <= elapsed < FALLBACK_BOUND_S


@pytest.mark.asyncio
async def test_a_click_waits_for_an_element_coming_in_from_past_both_viewport_edges(session: NotteSession) -> None:
    # a drawer sliding in from past the right and bottom edges over 6 s (past both for more than half of it): it is
    # on its way in, not kept outside
    html = (
        BUTTON.replace("fixed;", "fixed; transform: translate(3000px, 3000px); transition: transform 6s linear;")
        + "<script>requestAnimationFrame(() => requestAnimationFrame(() =>"
        + " { document.getElementById('target').style.transform = 'none' }))</script>"
    )
    elapsed, clicks, trusted = await click(session, html)

    assert (clicks, trusted) == (1, True)
    assert 5.0 <= elapsed < FALLBACK_BOUND_S


@pytest.mark.asyncio
async def test_a_click_in_a_frame_of_another_origin_waits_for_its_request(session: NotteSession) -> None:
    # a widget of another origin with a spinner over its button until its data arrives: the page does not watch that
    # frame's DOM or requests, so its cover is waited out as before
    page = session.window.page
    frame_html = (
        BUTTON + COVER + "<script>fetch('/data').then(() => document.getElementById('cover').remove())</script>"
    )
    await page.route(
        "http://top.test/",
        lambda route: route.fulfill(
            body='<iframe id="widget" src="http://widget.test/"></iframe>', content_type="text/html"
        ),
    )
    await page.route("http://widget.test/", lambda route: route.fulfill(body=frame_html, content_type="text/html"))
    await page.route("http://widget.test/data", serve_json(REQUEST_S))
    _ = await page.goto("http://top.test/")
    widget = page.frame(url="http://widget.test/")
    assert widget is not None
    action = ClickAction(
        selector={"css_selector": "#target", "in_iframe": True, "iframe_parent_css_selectors": ["#widget"]}
    )
    elapsed, clicks, trusted = await click(session, None, action=action, frame=widget)

    assert (clicks, trusted) == (1, True)
    assert REQUEST_S <= elapsed < FALLBACK_BOUND_S


@pytest.mark.asyncio
async def test_a_click_on_a_tab_selected_while_its_request_runs_waits_for_it(session: NotteSession) -> None:
    # a tab opened earlier is selected while its data request runs, with a spinner over its button until the data
    # arrives: the request started before the tab was shown, and is waited for all the same
    tab = await session.window.page.context.new_page()
    await tab.route("http://data.test/**", serve_json(REQUEST_S))
    await tab.set_content(
        BUTTON
        + COVER
        + "<script>fetch('http://data.test/data').then(() => document.getElementById('cover').remove())</script>"
    )
    session.window.page = tab
    elapsed, clicks, trusted = await click(session, None)

    assert (clicks, trusted) == (1, True)
    assert REQUEST_S <= elapsed < FALLBACK_BOUND_S
