"""Observe and act on cross-origin iframes, offline.

The main page (http://golden.test) embeds a cross-origin iframe (http://other.test) which embeds
another cross-origin iframe (back on http://golden.test). Hidden, zero-size and body-less frames are
added around them. Every response is served by `page.route`, other requests are aborted.
"""

from collections.abc import AsyncIterator, Callable, Iterator

import pytest
import pytest_asyncio
from notte_browser.dom import parsing
from notte_browser.dom.parsing import FRAME_EVALUATION_ATTEMPTS
from notte_browser.driver import ElementHandle, Error, Frame
from notte_browser.resolution import SelectorGenerator, resolve, set_selector_generator
from notte_browser.session import NotteSession
from notte_core.actions import ClickAction, FillAction
from notte_core.dom_tree import DomNode, NodeSelectors
from notte_core.observation import Observation
from patchright.async_api import Route

import notte

MAIN = "http://golden.test/"
CROSS = "http://other.test/form"
NESTED = "http://golden.test/nested"
BROKEN = "http://other.test/broken"

PAGES = {
    MAIN: """<body style="margin:0">
        <button id="main-btn" style="position:absolute;left:10px;top:10px">Main button</button>
        <div style="position:absolute;left:100px;top:150px">
          <iframe id="cross" src="http://other.test/form"
                  style="border:4px solid black;padding:6px;width:500px;height:300px"></iframe>
        </div>
        <iframe id="hidden" src="http://other.test/hidden" style="display:none"></iframe>
        <iframe id="zero" src="http://other.test/zero" width="0" height="0" style="border:0"></iframe>
        <iframe id="invisible" src="http://other.test/invisible" style="visibility:hidden"></iframe>
        <iframe id="broken" src="http://other.test/broken"
                style="position:absolute;left:700px;top:150px;width:200px;height:100px"></iframe>
        <iframe id="svg" src="http://other.test/image.svg"
                style="position:absolute;left:700px;top:300px;width:100px;height:100px"></iframe>
    </body>""",
    CROSS: """<body style="margin:0">
        <input id="name" placeholder="Your name" style="position:absolute;left:20px;top:30px;width:200px">
        <button id="go" style="position:absolute;left:20px;top:80px"
                onclick="document.getElementById('out').textContent = 'clicked:' + document.getElementById('name').value"
        >Submit form</button>
        <p id="out" style="position:absolute;left:300px;top:0"></p>
        <iframe id="nested" src="http://golden.test/nested"
                style="position:absolute;left:50px;top:120px;border:0;width:300px;height:100px"></iframe>
    </body>""",
    NESTED: """<body style="margin:0">
        <a id="link" href="#done" style="position:absolute;left:10px;top:10px">Nested link</a>
    </body>""",
    "http://other.test/hidden": "<button>Hidden frame button</button>",
    "http://other.test/zero": "<button>Zero frame button</button>",
    "http://other.test/invisible": "<button>Invisible frame button</button>",
    BROKEN: "<button>Broken frame button</button>",
}
SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><rect width="50" height="50"/></svg>'


async def _serve(route: Route) -> None:
    url = route.request.url
    if url == "http://other.test/image.svg":
        await route.fulfill(body=SVG, content_type="image/svg+xml")
    elif url in PAGES:
        await route.fulfill(body=PAGES[url], content_type="text/html")
    else:
        await route.abort()


@pytest_asyncio.fixture(loop_scope="function")
async def session() -> AsyncIterator[NotteSession]:
    async with notte.Session(headless=True, viewport_width=1280, viewport_height=720) as session:
        await session.window.page.route("**/*", _serve)
        _ = await session.window.page.goto(MAIN, wait_until="load")
        yield session


@pytest.fixture
def selector_generator() -> Iterator[Callable[[SelectorGenerator | None], None]]:
    yield set_selector_generator
    set_selector_generator(None)


def _frame(session: NotteSession, url: str) -> Frame:
    return next(frame for frame in session.window.page.frames if frame.url.startswith(url))


def _node(session: NotteSession, label: str) -> DomNode:
    assert session.snapshot is not None
    return next(node for node in session.snapshot.interaction_nodes() if node.inner_text() == label)


def _iframe_element(session: NotteSession, element_id: str) -> DomNode:
    assert session.snapshot is not None
    return next(
        node
        for node in session.snapshot.dom_node.flatten()
        if node.attributes is not None
        and node.attributes.tag_name == "iframe"
        and node.attributes.id_name == element_id
    )


def _selectors(node: DomNode) -> NodeSelectors:
    assert node.computed_attributes.selectors is not None
    return node.computed_attributes.selectors


def _labels(obs: Observation) -> list[str]:
    return [action.text_label or "" for action in obs.space.interaction_actions]


@pytest.mark.asyncio
async def test_cross_origin_iframe_elements_are_observed(session: NotteSession) -> None:
    obs = await session.aobserve()

    labels = _labels(obs)
    assert "Main button" in labels
    assert "Submit form" in labels
    assert "Nested link" in labels
    # ids follow the document order, frames included
    assert _node(session, "Main button").id == "B1"
    assert _node(session, "Submit form").id == "B2"
    assert _node(session, "Nested link").id == "L1"

    main_button = _selectors(_node(session, "Main button"))
    assert not main_button.in_iframe and main_button.iframe_parent_css_selectors == []

    # an iframe element is in an iframe only if its own document is
    cross_iframe = _selectors(_iframe_element(session, "cross"))
    assert not cross_iframe.in_iframe and cross_iframe.iframe_parent_css_selectors == []
    nested_iframe = _selectors(_iframe_element(session, "nested"))
    assert nested_iframe.in_iframe and nested_iframe.iframe_parent_css_selectors == [cross_iframe.css_selector]

    submit = _selectors(_node(session, "Submit form"))
    assert submit.in_iframe and submit.iframe_parent_css_selectors == [cross_iframe.css_selector]
    link = _selectors(_node(session, "Nested link"))
    assert link.in_iframe
    assert link.iframe_parent_css_selectors == [cross_iframe.css_selector, nested_iframe.css_selector]

    # the parent selectors locate the iframes, frame by frame
    page = session.window.page
    assert await page.locator(cross_iframe.css_selector).get_attribute("id") == "cross"
    nested_locator = page.frame_locator(cross_iframe.css_selector).locator(nested_iframe.css_selector)
    assert await nested_locator.get_attribute("id") == "nested"


@pytest.mark.asyncio
async def test_iframe_bboxes_are_in_main_viewport_coordinates(session: NotteSession) -> None:
    _ = await session.aobserve()

    # the content box of #cross starts at (100 + 4 border + 6 padding, 150 + 4 + 6)
    submit = _node(session, "Submit form").bbox
    assert submit is not None
    assert submit.absolute_x == pytest.approx(110 + 20, abs=0.5)
    assert submit.absolute_y == pytest.approx(160 + 80, abs=0.5)

    # #nested sits at (50, 120) in #cross
    link = _node(session, "Nested link").bbox
    assert link is not None
    assert link.absolute_x == pytest.approx(110 + 50 + 10, abs=0.5)
    assert link.absolute_y == pytest.approx(160 + 120 + 10, abs=0.5)

    # the element really is there: the main page hit-tests the point to the iframe
    hit = await session.window.page.evaluate(
        "([x, y]) => document.elementFromPoint(x, y)?.id", [link.absolute_x + 2, link.absolute_y + 2]
    )
    assert hit == "cross"


@pytest.mark.asyncio
async def test_hidden_and_body_less_iframes_are_skipped(session: NotteSession) -> None:
    obs = await session.aobserve()

    labels = _labels(obs)
    assert "Hidden frame button" not in labels
    assert "Zero frame button" not in labels
    assert "Invisible frame button" not in labels
    # the frame is evaluated, but an SVG document has no body: it is skipped, the others are kept
    assert "Broken frame button" in labels
    assert "Submit form" in labels


@pytest.mark.asyncio
async def test_a_frame_that_fails_to_evaluate_is_skipped(
    session: NotteSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    evaluate = parsing._evaluate  # pyright: ignore[reportPrivateUsage]
    attempts: list[str] = []

    async def failing_evaluate(frame: Frame, js_code: str, args: dict[str, object]):
        if frame.url == BROKEN:
            attempts.append(frame.url)
            raise Error("Execution context was destroyed")
        return await evaluate(frame, js_code, args)  # pyright: ignore[reportArgumentType]

    monkeypatch.setattr(parsing, "_evaluate", failing_evaluate)
    obs = await session.aobserve()

    labels = _labels(obs)
    assert "Broken frame button" not in labels
    assert "Submit form" in labels and "Nested link" in labels
    assert len(attempts) == 1  # the retries happen inside `_evaluate`


@pytest.mark.asyncio
async def test_evaluation_is_retried(session: NotteSession, monkeypatch: pytest.MonkeyPatch) -> None:
    failures: list[str] = []
    evaluate = Frame.evaluate

    async def flaky_evaluate(self: Frame, expression: str, arg: object = None, **kwargs: object) -> object:
        if self.url == BROKEN and len(failures) < FRAME_EVALUATION_ATTEMPTS - 1:
            failures.append(self.url)
            raise Error("Execution context was destroyed")
        return await evaluate(self, expression, arg, **kwargs)  # pyright: ignore[reportArgumentType]

    monkeypatch.setattr(Frame, "evaluate", flaky_evaluate)
    obs = await session.aobserve()

    assert len(failures) == FRAME_EVALUATION_ATTEMPTS - 1
    assert "Broken frame button" in _labels(obs)


@pytest.mark.asyncio
async def test_fill_and_click_inside_cross_origin_iframes(session: NotteSession) -> None:
    _ = await session.aobserve()

    _ = await session.aexecute(FillAction(id=_node(session, "Your name").id, value="Ada"), raise_on_failure=True)
    _ = await session.aexecute(ClickAction(id=_node(session, "Submit form").id), raise_on_failure=True)
    assert await _frame(session, CROSS).locator("#out").inner_text() == "clicked:Ada"

    _ = await session.aexecute(ClickAction(id=_node(session, "Nested link").id), raise_on_failure=True)
    assert _frame(session, NESTED).url == f"{NESTED}#done"


@pytest.mark.asyncio
async def test_no_element_handles_without_a_selector_generator(session: NotteSession) -> None:
    _ = await session.aobserve()
    assert session.snapshot is not None
    assert all(node.computed_attributes.handle is None for node in session.snapshot.dom_node.flatten())


async def _element_id(handle: ElementHandle, _selectors: NodeSelectors) -> str | None:
    return f"#{await handle.get_attribute('id')}"


@pytest.mark.asyncio
async def test_selector_generator_is_used_to_resolve_nodes(
    session: NotteSession, selector_generator: Callable[[SelectorGenerator | None], None]
) -> None:
    calls: list[NodeSelectors] = []

    async def generator(handle: ElementHandle, selectors: NodeSelectors) -> str | None:
        calls.append(selectors)
        return await _element_id(handle, selectors)

    selector_generator(generator)
    _ = await session.aobserve()
    submit = _node(session, "Submit form")
    assert submit.computed_attributes.handle is not None

    action = await resolve(ClickAction(id=submit.id), session.snapshot)
    assert isinstance(action, ClickAction) and action.selector is not None
    cross_css = _selectors(_iframe_element(session, "cross")).css_selector
    # the generated selector is prefixed with the parent iframes
    assert action.selector.playwright_selector == f"css={cross_css} >> internal:control=enter-frame >> #go"
    assert calls == [_selectors(submit)]
    # the snapshot keeps its own selectors
    assert _selectors(submit).playwright_selector is None

    # the generated selectors are used to act, in both frames
    _ = await session.aexecute(FillAction(id=_node(session, "Your name").id, value="Grace"), raise_on_failure=True)
    _ = await session.aexecute(ClickAction(id=submit.id), raise_on_failure=True)
    assert await _frame(session, CROSS).locator("#out").inner_text() == "clicked:Grace"
    _ = await session.aexecute(ClickAction(id=_node(session, "Main button").id), raise_on_failure=True)
    assert len(calls) == 4


@pytest.mark.asyncio
async def test_page_rooted_generated_selectors_are_kept(
    session: NotteSession, selector_generator: Callable[[SelectorGenerator | None], None]
) -> None:
    async def generator(handle: ElementHandle, selectors: NodeSelectors) -> str | None:
        return f"iframe#cross >> internal:control=enter-frame >> {await _element_id(handle, selectors)}"

    selector_generator(generator)
    _ = await session.aobserve()
    action = await resolve(ClickAction(id=_node(session, "Submit form").id), session.snapshot)
    assert isinstance(action, ClickAction) and action.selector is not None
    assert action.selector.playwright_selector == "iframe#cross >> internal:control=enter-frame >> #go"


async def _returning_none(_handle: ElementHandle, _selectors: NodeSelectors) -> str | None:
    return None


async def _raising(_handle: ElementHandle, _selectors: NodeSelectors) -> str | None:
    raise RuntimeError("no selector for you")


@pytest.mark.asyncio
@pytest.mark.parametrize("generator", [_returning_none, _raising], ids=["none", "exception"])
async def test_selector_generator_falls_back_to_css_and_xpath(
    session: NotteSession,
    selector_generator: Callable[[SelectorGenerator | None], None],
    generator: SelectorGenerator,
) -> None:
    selector_generator(generator)
    _ = await session.aobserve()
    submit = _node(session, "Submit form")

    action = await resolve(ClickAction(id=submit.id), session.snapshot)
    assert isinstance(action, ClickAction) and action.selector is not None
    assert action.selector.playwright_selector is None
    assert action.selector == _selectors(submit)

    _ = await session.aexecute(FillAction(id=_node(session, "Your name").id, value="Alan"), raise_on_failure=True)
    _ = await session.aexecute(ClickAction(id=submit.id), raise_on_failure=True)
    assert await _frame(session, CROSS).locator("#out").inner_text() == "clicked:Alan"


@pytest.mark.asyncio
async def test_canonical_shadow_node_resolves_and_executes(session: NotteSession) -> None:
    await session.window.page.set_content('<div id="host"></div>')
    _ = await session.window.page.evaluate(
        """() => {
            const host = document.querySelector('#host');
            const shadow = host.attachShadow({mode: 'open'});
            shadow.innerHTML = '<button aria-label="Accessible name"><span>Visible label</span></button>';
            shadow.querySelector('button').onclick = () => { host.dataset.clicked = 'yes'; };
        }"""
    )
    _ = await session.aobserve()
    node = _node(session, "Visible label")
    assert node.id is not None and node.parent is not None and node.children
    assert node.text == "Accessible name"
    assert session.snapshot.dom_node.find(node.id) is node
    assert _selectors(node).in_shadow_root
    resolved = await resolve(ClickAction(id=node.id), session.snapshot)
    assert resolved.text_label == "Visible label"
    _ = await session.aexecute(resolved, raise_on_failure=True)
    assert await session.window.page.locator("#host").get_attribute("data-clicked") == "yes"
