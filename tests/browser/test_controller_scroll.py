from collections.abc import AsyncIterator
from typing import cast

import pytest
import pytest_asyncio
from notte_browser.controller import BrowserController
from notte_browser.errors import ScrollActionFailedError
from notte_browser.playwright_async_api import Page, async_playwright
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
@pytest.mark.parametrize("layout", ["document", "panel", "shadow", "iframe"])
@pytest.mark.parametrize("up", [False, True])
@pytest.mark.parametrize("amount", [250, None])
async def test_scroll_recognizes_actual_container_movement(
    page: Page, layout: str, up: bool, amount: int | None
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

    action = ScrollUpAction(amount=amount) if up else ScrollDownAction(amount=amount)
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
