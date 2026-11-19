"""An action located by a CSS or XPath selector its caller wrote waits for the element, as a Playwright selector does.

A script acts on pages that are still rendering: the search box of a page that hydrates, the results a click
loads. Such a selector was looked up once and failed at once when the element was not there yet, and reported
"count=0" when it matched several elements.
"""

import asyncio
import time
from urllib.parse import quote

import notte_browser.dom.locate as locate_module
import notte_browser.execution as execution_module
import pytest
from notte_browser.dom.locate import locate_element
from notte_browser.driver import Locator, Page
from notte_browser.errors import AmbiguousSelectorError, InvalidLocatorRuntimeError
from notte_browser.session import NotteSession
from notte_core.actions import ClickAction, FillAction
from notte_core.dom_tree import NodeSelectors

# the element is added this long after the page loaded
RENDER_MS = 700
LATE_PAGE = f"""
<script>
  setTimeout(() => {{
    document.body.insertAdjacentHTML(
      "beforeend",
      '<button id="late" onclick="document.body.dataset.clicked = 1">Search</button><input id="query">'
    );
  }}, {RENDER_MS});
</script>
"""
TWINS_PAGE = '<input class="max" placeholder="max"><input class="max" placeholder="max">'


def _url(html: str) -> str:
    return f"data:text/html,{quote(html)}"


@pytest.mark.parametrize(
    "selector",
    ["css=#late", "xpath=//button[@id='late']", {"css_selector": "#late"}, {"xpath_selector": "//button[@id='late']"}],
)
@pytest.mark.asyncio
async def test_a_click_waits_for_an_element_rendered_later(selector: str | dict[str, str]) -> None:
    async with NotteSession(headless=True) as session:
        _ = await session.window.page.goto(_url(LATE_PAGE))
        result = await session.aexecute(ClickAction(selector=selector), raise_on_failure=False)  # pyright: ignore[reportArgumentType]
        clicked = await session.window.page.evaluate("() => document.body.dataset.clicked")

    assert result.success, result.message
    assert clicked == "1"


@pytest.mark.asyncio
async def test_a_fill_waits_for_an_element_rendered_later() -> None:
    async with NotteSession(headless=True) as session:
        _ = await session.window.page.goto(_url(LATE_PAGE))
        result = await session.aexecute(FillAction(selector="css=#query", value="bike"), raise_on_failure=False)
        value = await session.window.page.locator("#query").input_value()

    assert result.success, result.message
    assert value == "bike"


@pytest.mark.asyncio
async def test_an_element_that_never_renders_fails_after_the_wait() -> None:
    async with NotteSession(headless=True) as session:
        _ = await session.window.page.goto(_url("<p>nothing to click</p>"))
        started = time.monotonic()
        result = await session.aexecute(ClickAction(selector="css=#missing", timeout=1000), raise_on_failure=False)
        elapsed = time.monotonic() - started

    assert not result.success
    assert isinstance(result.exception, InvalidLocatorRuntimeError)
    assert "could not be located" in result.message
    # three fifths of the timeout: the rest is held back for the interaction
    assert elapsed >= 0.55


@pytest.mark.asyncio
async def test_the_wait_does_not_outlast_its_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    """The last pause is cut to what is left, so the action's own timeout does not end the lookup first."""
    pauses: list[float] = []
    sleep = asyncio.sleep

    async def record(delay: float) -> None:
        pauses.append(delay)
        await sleep(delay)

    monkeypatch.setattr(locate_module.asyncio, "sleep", record)
    async with NotteSession(headless=True) as session:
        _ = await session.window.page.goto(_url("<p>nothing to click</p>"))
        with pytest.raises(InvalidLocatorRuntimeError):
            _ = await locate_element(
                session.window.page, NodeSelectors.from_unique_selector("css=#missing"), wait_ms=50
            )

    # The wait is shorter than a whole pause (100 ms): any pause taken has to be cut to what is left. A lookup too
    # slow to leave time for a pause takes none, with or without the cut.
    assert all(pause <= 0.05 for pause in pauses)


@pytest.mark.asyncio
async def test_an_element_in_a_frame_added_later_is_waited_for() -> None:
    page = f"""
    <script>
      setTimeout(() => {{
        const frame = document.createElement("iframe");
        frame.id = "frame";
        frame.srcdoc = '<button id="inside" onclick="parent.document.body.dataset.clicked = 1">Go</button>';
        document.body.appendChild(frame);
      }}, {RENDER_MS});
    </script>
    """
    selector = {"css_selector": "#inside", "iframe_parent_css_selectors": ["#frame"], "in_iframe": True}
    async with NotteSession(headless=True) as session:
        _ = await session.window.page.goto(_url(page))
        result = await session.aexecute(ClickAction(selector=selector), raise_on_failure=False)  # pyright: ignore[reportArgumentType]
        clicked = await session.window.page.evaluate("() => document.body.dataset.clicked")

    assert result.success, result.message
    assert clicked == "1"


@pytest.mark.asyncio
async def test_a_selector_matching_several_elements_is_refused_as_ambiguous() -> None:
    async with NotteSession(headless=True) as session:
        _ = await session.window.page.goto(_url(TWINS_PAGE))
        result = await session.aexecute(FillAction(selector="css=input.max", value="300"), raise_on_failure=False)

    assert not result.success
    assert isinstance(result.exception, AmbiguousSelectorError)
    assert "The selector css=input.max matched 2 elements" in result.message


@pytest.mark.asyncio
async def test_a_unique_selector_wins_over_an_ambiguous_one() -> None:
    selectors = NodeSelectors.from_unique_selector("css=input.max").model_copy(
        update={"xpath_selector": "(//input[@class='max'])[2]"}
    )
    async with NotteSession(headless=True) as session:
        _ = await session.window.page.goto(_url(TWINS_PAGE))
        locator = await locate_element(session.window.page, selectors, wait_ms=1000)
        index = await locator.evaluate("el => [...document.querySelectorAll('input')].indexOf(el)")

    assert index == 1


@pytest.mark.asyncio
async def test_only_a_selector_the_caller_wrote_is_waited_for(monkeypatch: pytest.MonkeyPatch) -> None:
    """An observed element was on the page: when its selectors match nothing it is looked for again by what it
    is, not waited for."""
    waits: list[float | None] = []

    async def spy(page: Page, selectors: NodeSelectors, *, wait_ms: float | None = None) -> Locator:
        waits.append(wait_ms)
        return await locate_element(page, selectors, wait_ms=wait_ms)

    monkeypatch.setattr(execution_module, "locate_element", spy)
    async with NotteSession(headless=True) as session:
        _ = await session.window.page.goto(_url('<button id="go">Go</button>'))
        observation = await session.aobserve()
        observed = await session.aexecute(
            type="click", id=observation.space.interaction_actions[0].id, raise_on_failure=False
        )
        written = await session.aexecute(ClickAction(selector="css=#go", timeout=5000), raise_on_failure=False)

    assert observed.success, observed.message
    assert written.success, written.message
    assert waits[0] is None
    # two fifths of the timeout are held back: one for the click, one for its fallback
    assert waits[1] is not None and 0 < waits[1] <= 3000
