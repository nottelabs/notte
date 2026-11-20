"""A click on an element that stays hidden, covered or out of the viewport falls back to a script click at once, instead
of after four fifths of its timeout; a cover of a moment still gets the pointer click (`execution._pointer_click`)."""

import asyncio
import time
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from notte_browser.execution import _CLICK_BLOCKED_MS, _CLICK_FIRST_SLICE_MS
from notte_browser.session import NotteSession
from notte_core.actions import ClickAction
from patchright.async_api import Route

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


async def click(session: NotteSession, html: str) -> tuple[float, int, bool | None]:
    """Clicks `#target` on a page of `html`: how long the click took (s), how many clicks the button got and whether
    the last one was the pointer's."""
    await session.window.page.set_content(html)
    start = time.monotonic()
    result = await session.aexecute(ClickAction(selector="#target"), raise_on_failure=False)
    elapsed = time.monotonic() - start
    assert result.success, result.message
    clicks: int = await session.window.page.evaluate("Number(document.body.dataset.clicks || 0)")
    trusted: str | None = await session.window.page.evaluate("document.body.dataset.trusted ?? null")
    return elapsed, clicks, None if trusted is None else trusted == "true"


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
