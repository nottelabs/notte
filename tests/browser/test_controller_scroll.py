import ast
import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import notte_browser.execution as execution_module
import pytest
import pytest_asyncio
from notte_browser.driver import Error, Page, async_playwright
from notte_browser.errors import ScrollActionFailedError
from notte_browser.execution import execute_browser_action
from notte_browser.window import BrowserWindow, BrowserWindowOptions
from notte_core.actions import ScrollDownAction, ScrollUpAction
from notte_core.types import LocalSessionStartRequest

PANEL_HTML = """
<style>
    body { margin: 0; overflow: hidden; }
    #panel { width: 600px; height: 400px; overflow: auto; }
    #content { height: 3000px; }
</style>
<div id="panel"><div id="content">Scrollable content</div></div>
"""


@pytest_asyncio.fixture(loop_scope="function")
async def page() -> AsyncIterator[Page]:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(channel="chromium", headless=True)
        try:
            yield await browser.new_page(viewport={"width": 800, "height": 600})
        finally:
            await browser.close()


async def scroll(page: Page, action: ScrollDownAction | ScrollUpAction) -> bool:
    window = BrowserWindow(page, BrowserWindowOptions.from_request(LocalSessionStartRequest()))
    return await execute_browser_action(window, action)


@pytest.mark.asyncio
@pytest.mark.parametrize("moved", [False, True])
async def test_scroll_deadline_bounds_a_blocked_read(monkeypatch: pytest.MonkeyPatch, moved: bool) -> None:
    monkeypatch.setattr(execution_module, "SCROLL_CAP_MS", 50)
    reads = 0
    blocked = asyncio.Event()

    async def read() -> tuple[bool, list[list[float | None]]]:
        nonlocal reads
        reads += 1
        if reads == 1:
            return moved, [[0]]
        _ = await blocked.wait()
        raise AssertionError("The blocked read must be cancelled")

    async with asyncio.timeout(0.5):
        assert await execution_module._scroll_ended(read) is moved
    assert reads == 2


@pytest.mark.asyncio
async def test_scroll_does_not_hide_a_reader_timeout() -> None:
    async def read() -> tuple[bool, list[list[float | None]]]:
        raise TimeoutError("reader failed")

    with pytest.raises(TimeoutError, match="reader failed"):
        _ = await execution_module._scroll_ended(read)


@pytest.mark.asyncio
async def test_targeted_scroll_boundary_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(execution_module, "SCROLL_START_MS", 0)
    monkeypatch.setattr(execution_module, "SCROLL_CAP_MS", 50)
    blocked = asyncio.Event()
    boundary_calls = 0

    async def evaluate(expression: str, _delta: float | None = None) -> float | bool | None:
        nonlocal boundary_calls
        if expression == execution_module._SCROLL_BOUNDARY:
            boundary_calls += 1
            if boundary_calls > 1:
                _ = await blocked.wait()
            return False
        if expression == "element => element.scrollTop":
            return 0
        return None

    target = AsyncMock()
    target.evaluate.side_effect = evaluate
    window = MagicMock()
    window.page.evaluate = AsyncMock()
    window.page.locator.return_value.evaluate_handle = AsyncMock(return_value=target)
    async with asyncio.timeout(0.5):
        with pytest.raises(ScrollActionFailedError):
            _ = await execute_browser_action(window, ScrollDownAction(selector="#panel", amount=100))
    assert boundary_calls == 2
    target.dispose.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("previous_page", ["restrictive-csp", "fixed-layout"])
async def test_documented_scroll_fixture_replaces_previous_page_styles(page: Page, previous_page: str) -> None:
    source = Path(__file__).resolve().parents[2] / "docs/src/testers/browser-controls/scroll_down.py"
    setup = next(
        node
        for node in ast.walk(ast.parse(source.read_text()))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "evaluate_js"
    )
    code = ast.literal_eval(setup.args[0])
    fixture_url = "https://scroll-fixture.notte.test/"
    html = "<!doctype html><p>Previous page</p>"
    headers = {}
    if previous_page == "restrictive-csp":
        headers["Content-Security-Policy"] = "style-src 'none'"
    else:
        html = (
            "<!doctype html><head><style>html,body {height:100%; overflow:hidden}</style></head>"
            "<body>Previous page</body>"
        )

    async def serve_fixture(route):
        if route.request.url == fixture_url:
            await route.fulfill(status=200, content_type="text/html", headers=headers, body=html)
        else:
            await route.abort()

    await page.route("**/*", serve_fixture)
    await page.goto(fixture_url, wait_until="domcontentloaded")
    await page.evaluate(code)
    assert await page.evaluate("document.scrollingElement.scrollHeight > window.innerHeight")

    for selector in (None, "html"):
        assert await scroll(page, ScrollDownAction(selector=selector))
        assert await page.evaluate("window.scrollY") > 0
        assert await scroll(page, ScrollUpAction(selector=selector))
        assert await page.evaluate("window.scrollY") == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("targeted", [False, True])
@pytest.mark.parametrize("layout", ["document", "panel", "shadow", "iframe"])
@pytest.mark.parametrize("up", [False, True])
@pytest.mark.parametrize("amount", [250, None])
async def test_scroll_recognizes_actual_container_movement(
    page: Page, layout: str, up: bool, amount: int | None, targeted: bool
) -> None:
    frame = page.main_frame
    if layout == "document":
        await page.set_content('<div style="height:3000px">Scrollable document</div>')
        target = "document.scrollingElement"
    elif layout == "panel":
        await page.set_content(PANEL_HTML)
        target = "document.querySelector('#panel')"
    elif layout == "shadow":
        await page.set_content('<style>body { margin: 0; overflow: hidden; }</style><div id="host"></div>')
        await page.evaluate(
            "html => document.querySelector('#host').attachShadow({mode: 'open'}).innerHTML = html", PANEL_HTML
        )
        target = "document.querySelector('#host').shadowRoot.querySelector('#panel')"
    else:
        await page.set_content('<style>body { margin: 0; }</style><iframe style="width:650px;height:450px"></iframe>')
        frame = page.frames[1]
        await frame.set_content(PANEL_HTML)
        target = "document.querySelector('#panel')"

    if up:
        await frame.evaluate(f"{target}.scrollTop = 1200")
    await page.mouse.move(100, 100)
    before = cast(int, await frame.evaluate(f"{target}.scrollTop"))

    selector = (
        {
            "document": "html",
            "panel": "#panel",
            "shadow": "#host >> #panel",
            "iframe": "iframe >> internal:control=enter-frame >> #panel",
        }[layout]
        if targeted
        else None
    )
    if targeted:
        await page.mouse.move(750, 550)
    action = (
        ScrollUpAction(amount=amount, selector=selector) if up else ScrollDownAction(amount=amount, selector=selector)
    )
    assert await scroll(page, action)

    after = cast(int, await frame.evaluate(f"{target}.scrollTop"))
    assert after < before if up else after > before
    if layout != "document":
        assert await page.evaluate("window.scrollY") == 0


# The page's content is a list in a scroll container, away from the viewport's corner, beside a smaller one
LIST_PAGE_HTML = """
<style>
    body { margin: 0; overflow: hidden; display: flex; }
    #side { width: 150px; height: 200px; overflow: auto; }
    #list { margin-top: 120px; width: 500px; height: 420px; overflow: auto; }
</style>
<div id="side"><div style="height: 1000px">Filters</div></div>
<div id="list"><div style="height: 5000px">Orders</div></div>
"""


@pytest.mark.asyncio
@pytest.mark.parametrize("up", [False, True])
async def test_scroll_reaches_the_largest_scroll_container_away_from_the_mouse(page: Page, up: bool) -> None:
    await page.set_content(LIST_PAGE_HTML)
    await page.mouse.move(400, 50)
    if up:
        await page.evaluate("document.querySelector('#list').scrollTop = 2000")

    assert await scroll(page, ScrollUpAction() if up else ScrollDownAction())

    top = await page.locator("#list").evaluate("list => list.scrollTop")
    assert top < 2000 if up else top > 0
    assert await page.locator("#side").evaluate("side => side.scrollTop") == 0


@pytest.mark.asyncio
async def test_scroll_up_reaches_a_reversed_list_away_from_the_mouse(page: Page) -> None:
    # a chat log: newest at the bottom, where it starts (scrollTop 0); older messages above (negative scrollTop)
    await page.set_content(
        LIST_PAGE_HTML
        + "<style>#list { display: flex; flex-direction: column-reverse } #list > div { flex-shrink: 0 }</style>"
    )
    await page.mouse.move(400, 50)
    assert await scroll(page, ScrollUpAction())
    assert await page.locator("#list").evaluate("list => list.scrollTop") < 0
    with pytest.raises(ScrollActionFailedError):
        # at its bottom already, and the other container cannot reach it
        await page.locator("#side").evaluate("side => side.scrollTop = side.scrollHeight")
        await page.locator("#list").evaluate("list => list.scrollTop = 0")
        await scroll(page, ScrollDownAction())


@pytest.mark.asyncio
async def test_scroll_skips_a_container_clipped_out_of_view(page: Page) -> None:
    # the larger list is mostly hidden by its parent: only a 40 px strip of it shows, so the smaller one is scrolled
    await page.set_content("""
        <style>
            body { margin: 0; overflow: hidden; display: flex; }
            #clip { margin-top: 120px; width: 600px; height: 40px; overflow: hidden; }
            #big { height: 500px; overflow: auto; }
            #small { margin-top: 120px; width: 150px; height: 300px; overflow: auto; }
        </style>
        <div id="clip"><div id="big"><div style="height: 5000px">Big</div></div></div>
        <div id="small"><div style="height: 3000px">Small</div></div>
    """)
    await page.mouse.move(700, 20)
    assert await scroll(page, ScrollDownAction(amount=200))
    assert await page.locator("#small").evaluate("small => small.scrollTop") > 0


@pytest.mark.asyncio
async def test_scroll_reaches_a_list_inside_a_frame_away_from_the_mouse(page: Page) -> None:
    await page.set_content(
        '<style>body { margin: 0; overflow: hidden }</style><iframe style="margin: 100px 0 0 150px; width: 600px; height: 450px"></iframe>'
    )
    frame = page.frames[1]
    await frame.set_content(LIST_PAGE_HTML)
    await page.mouse.move(20, 20)
    assert await scroll(page, ScrollDownAction())
    assert await frame.locator("#list").evaluate("list => list.scrollTop") > 0


@pytest.mark.asyncio
@pytest.mark.parametrize("nested", [False, True])
async def test_scroll_reaches_a_frame_clipped_by_an_ancestor(page: Page, nested: bool) -> None:
    await page.set_content(
        "<style>body { margin: 0; overflow: hidden }</style>"
        '<div style="margin: 100px; width: 600px; height: 100px; overflow: hidden">'
        '<iframe style="border: 0; width: 600px; height: 450px"></iframe></div>'
    )
    frame = page.frames[1]
    if nested:
        await frame.set_content(
            "<style>body { margin: 0; overflow: hidden }</style>"
            '<iframe style="margin: 20px; border: 0; width: 550px; height: 400px"></iframe>'
        )
        frame = frame.child_frames[0]
    await frame.set_content(PANEL_HTML)
    await page.mouse.move(10, 10)

    assert await scroll(page, ScrollDownAction(amount=200))
    assert await frame.locator("#panel").evaluate("panel => panel.scrollTop") > 0


@pytest.mark.asyncio
@pytest.mark.parametrize("up", [False, True])
async def test_scroll_still_fails_at_panel_boundary(page: Page, up: bool) -> None:
    await page.set_content(PANEL_HTML)
    if not up:
        await page.evaluate("document.querySelector('#panel').scrollTop = 3000")
    await page.mouse.move(100, 100)

    action = ScrollUpAction(amount=250) if up else ScrollDownAction(amount=250)
    with pytest.raises(ScrollActionFailedError):
        await scroll(page, action)


@pytest.mark.asyncio
async def test_scroll_still_fails_on_non_scrollable_page(page: Page) -> None:
    await page.set_content("<p>No scrolling here</p>")
    await page.mouse.move(100, 100)

    with pytest.raises(ScrollActionFailedError):
        await scroll(page, ScrollDownAction(amount=250))


@pytest.mark.asyncio
async def test_prevented_wheel_does_not_count_as_scroll(page: Page) -> None:
    await page.set_content(PANEL_HTML)
    await page.evaluate("window.addEventListener('wheel', event => event.preventDefault(), {passive: false})")
    await page.mouse.move(100, 100)

    with pytest.raises(ScrollActionFailedError):
        await scroll(page, ScrollDownAction(amount=250))
    assert await page.locator("#panel").evaluate("panel => panel.scrollTop") == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("up", [False, True])
@pytest.mark.parametrize("offscreen", [False, True])
async def test_targeted_boundary_is_noop_without_scrolling_parent(page: Page, up: bool, offscreen: bool) -> None:
    await page.set_content(PANEL_HTML + '<style>body {overflow:auto}</style><div style="height:3000px"></div>')
    if offscreen:
        await page.locator("#panel").evaluate("panel => panel.style.marginTop = '1200px'")
    if not up:
        await page.locator("#panel").evaluate("panel => panel.scrollTop = panel.scrollHeight")
    before = await page.locator("#panel").evaluate("panel => panel.scrollTop")
    action = ScrollUpAction(selector="#panel", amount=250) if up else ScrollDownAction(selector="#panel", amount=250)

    assert await scroll(page, action)
    assert await scroll(page, action)
    assert await page.locator("#panel").evaluate("panel => panel.scrollTop") == before
    assert await page.evaluate("window.scrollY") == 0


@pytest.mark.asyncio
async def test_targeted_scroll_rejects_non_scrollable_element(page: Page) -> None:
    await page.set_content('<div id="static">Not a scroll container</div>')
    with pytest.raises(ScrollActionFailedError):
        await scroll(page, ScrollDownAction(selector="#static", amount=250))


@pytest.mark.asyncio
async def test_targeted_scroll_rejects_missing_selector(page: Page, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        execution_module, "config", execution_module.config.model_copy(update={"timeout_action_ms": 100})
    )
    with pytest.raises(Error):
        await scroll(page, ScrollDownAction(selector="#missing", amount=250))


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["moved", "no-op", "setup-error"])
async def test_scroll_releases_trackers_on_success_and_failure(outcome: str) -> None:
    handle = AsyncMock()
    # whether the wheel scrolled, and where the scroll is
    handle.evaluate.return_value = [outcome == "moved", [0]]
    frame = MagicMock()
    frame.evaluate_handle = AsyncMock(return_value=handle)
    # no scroll container in view to send the wheel over
    frame.evaluate = AsyncMock(return_value=None)
    window = MagicMock()
    window.page.frames = [frame]
    window.page.main_frame = frame
    window.page.evaluate = AsyncMock()
    window.page.wait_for_timeout = AsyncMock()
    window.page.mouse.wheel = AsyncMock()
    if outcome == "setup-error":
        other_frame = MagicMock()
        other_frame.evaluate_handle = AsyncMock(side_effect=RuntimeError("setup failed"))
        window.page.frames.append(other_frame)
    if outcome == "moved":
        assert await execute_browser_action(window, ScrollDownAction(amount=100))
    else:
        error = RuntimeError if outcome == "setup-error" else ScrollActionFailedError
        with pytest.raises(error):
            await execute_browser_action(window, ScrollDownAction(amount=100))
    handle.evaluate.assert_any_await("tracker => tracker.dispose()")
    handle.dispose.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["setup", "check"])
async def test_scroll_ignores_unrelated_destroyed_frame(phase: str) -> None:
    handle = AsyncMock()
    handle.evaluate.return_value = [True, [0]]
    good_frame = MagicMock()
    good_frame.evaluate_handle = AsyncMock(return_value=handle)
    good_frame.evaluate = AsyncMock(return_value=None)
    lost_frame = MagicMock()
    lost_frame.is_detached.return_value = False
    lost_handle = AsyncMock()
    error = Error("Execution context was destroyed, most likely because of a navigation")
    lost_frame.evaluate_handle = AsyncMock(return_value=lost_handle)
    if phase == "setup":
        lost_frame.evaluate_handle.side_effect = error
    else:
        lost_handle.evaluate.side_effect = error
    window = MagicMock()
    window.page.frames = [lost_frame, good_frame]
    window.page.evaluate = AsyncMock()
    window.page.wait_for_timeout = AsyncMock()
    window.page.mouse.wheel = AsyncMock()

    assert await execute_browser_action(window, ScrollDownAction(amount=100))
    window.page.mouse.wheel.assert_awaited_once()
    handle.dispose.assert_awaited_once()
    if phase == "check":
        lost_handle.dispose.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("up", [False, True])
@pytest.mark.parametrize("boundary", [False, True])
async def test_targeted_scroll_handles_reversed_panel(page: Page, up: bool, boundary: bool) -> None:
    await page.set_content(
        PANEL_HTML
        + """
        <style>
            #panel { display: flex; flex-direction: column-reverse; }
            #content { flex-shrink: 0; }
        </style>
    """
    )
    panel = page.locator("#panel")
    position = (-2600 if up else 0) if boundary else -1200
    await panel.evaluate("(panel, position) => panel.scrollTop = position", position)
    assert await panel.evaluate("panel => panel.scrollTop") == position
    action = ScrollUpAction(selector="#panel", amount=250) if up else ScrollDownAction(selector="#panel", amount=250)
    assert await scroll(page, action)
    after = await panel.evaluate("panel => panel.scrollTop")
    if boundary:
        assert after == position
    else:
        assert after < position if up else after > position


@pytest.mark.asyncio
@pytest.mark.parametrize("up", [False, True])
async def test_targeted_scroll_moves_parent_instead_of_nested_child(page: Page, up: bool) -> None:
    await page.set_content(
        PANEL_HTML
        + """
        <style> #child {height: 800px; overflow: auto;} </style>
        <script>
            document.querySelector('#content').innerHTML =
                '<div id="child"><div style="height:3000px">Nested content</div></div>';
        </script>
    """
    )
    panel = page.locator("#panel")
    await panel.evaluate("panel => panel.scrollTop = 300")
    await page.locator("#child").evaluate("child => child.scrollTop = 500")
    await page.mouse.move(750, 550)
    action = ScrollUpAction(selector="#panel", amount=100) if up else ScrollDownAction(selector="#panel", amount=100)
    assert await scroll(page, action)
    assert await panel.evaluate("panel => panel.scrollTop") == (200 if up else 400)
    assert await page.locator("#child").evaluate("child => child.scrollTop") == 500
    assert await page.evaluate("window.scrollY") == 0


@pytest.mark.asyncio
async def test_targeted_scroll_fails_when_container_clips_scrolling(page: Page) -> None:
    await page.set_content(PANEL_HTML + "<style>#panel {overflow:clip}</style>")
    with pytest.raises(ScrollActionFailedError):
        await scroll(page, ScrollDownAction(selector="#panel", amount=250))
    assert await page.locator("#panel").evaluate("panel => panel.scrollTop") == 0
