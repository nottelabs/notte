from collections.abc import AsyncIterator
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import notte_browser.controller as controller_module
import pytest
import pytest_asyncio
from notte_browser.controller import BrowserController
from notte_browser.errors import ScrollActionFailedError
from notte_browser.playwright_async_api import Error, Page, async_playwright
from notte_browser.window import BrowserResource, BrowserWindow
from notte_core.actions import ScrollDownAction, ScrollUpAction

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
    resource = BrowserResource.model_construct(page=page, options=None)
    window = BrowserWindow(resource=resource)
    return await BrowserController(verbose=False).execute_browser_action(window, action)


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
        controller_module, "config", controller_module.config.model_copy(update={"timeout_action_ms": 100})
    )
    with pytest.raises(Error):
        await scroll(page, ScrollDownAction(selector="#missing", amount=250))


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["moved", "no-op", "setup-error"])
async def test_scroll_releases_trackers_on_success_and_failure(outcome: str) -> None:
    handle = AsyncMock()
    handle.evaluate.return_value = outcome == "moved"
    frame = MagicMock()
    frame.evaluate_handle = AsyncMock(return_value=handle)
    window = MagicMock()
    window.page.frames = [frame]
    window.page.evaluate = AsyncMock()
    window.page.wait_for_timeout = AsyncMock()
    window.page.mouse.wheel = AsyncMock()
    if outcome == "setup-error":
        other_frame = MagicMock()
        other_frame.evaluate_handle = AsyncMock(side_effect=RuntimeError("setup failed"))
        window.page.frames.append(other_frame)
    controller = BrowserController(verbose=False)
    if outcome == "moved":
        assert await controller.execute_browser_action(window, ScrollDownAction(amount=100))
    else:
        error = RuntimeError if outcome == "setup-error" else ScrollActionFailedError
        with pytest.raises(error):
            await controller.execute_browser_action(window, ScrollDownAction(amount=100))
    handle.evaluate.assert_any_await("tracker => tracker.dispose()")
    handle.dispose.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["setup", "check"])
async def test_scroll_ignores_unrelated_destroyed_frame(phase: str) -> None:
    handle = AsyncMock()
    handle.evaluate.return_value = True
    good_frame = MagicMock()
    good_frame.evaluate_handle = AsyncMock(return_value=handle)
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

    assert await BrowserController(verbose=False).execute_browser_action(window, ScrollDownAction(amount=100))
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
