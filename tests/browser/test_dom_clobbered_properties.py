"""`observe()` reads elements and the document through the DOM, not through what the page names.

A `<form>` exposes its controls as properties named after their `name` or `id`, and they win over the
form's own properties and methods: with `<input type="hidden" name="children">` (a trip search form),
`form.children` is the input. `buildDomNode.js` read such properties on every element, forms included,
so the DOM build threw (`children is not iterable`), and observe failed with it; with other names it
left the form out, or gave its controls wrong XPaths. In the page's own world, the document does the
same for named images (`<img name="createRange">` is `document.createRange`).
"""

import json
from urllib.parse import quote

import pytest
from notte_browser.dom.parsing import DOM_TREE_JS
from notte_browser.session import NotteSession
from notte_core.config import BrowserBackend, config

# form control names that are DOM properties or methods the DOM build reads on an element
CLOBBERING_NAMES = [
    "children",
    "childNodes",
    "parentNode",
    "parentElement",
    "nodeType",
    "nodeName",
    "tagName",
    "localName",
    "id",
    "shadowRoot",
    "getAttribute",
    "hasAttribute",
    "getAttributeNames",
    "matches",
    "closest",
    "contains",
    "getBoundingClientRect",
    "getClientRects",
    "checkVisibility",
    "classList",
    "offsetWidth",
    "disabled",
]


def _form(name: str) -> str:
    return f"""
        <form style="overflow: auto">
          <input type="hidden" name="{name}" value="0">
          <label>Destination <input name="destination"></label>
          <button type="button" onclick="document.title = 'searched'">Search</button>
        </form>
        <p>After the form</p>
    """


async def _observe_form(session: NotteSession, name: str) -> list[tuple[str, str]]:
    """Observes the form and returns each offered control's label and XPath."""
    _ = await session.window.page.goto(f"data:text/html,{quote(_form(name))}")
    obs = await session.aobserve()
    assert "After the form" in [node.text for node in session.snapshot.dom_node.flatten()], name

    controls: list[tuple[str, str]] = []
    for action in obs.space.interaction_actions:
        node = session.snapshot.dom_node.find(action.id)
        assert node is not None and node.computed_attributes.selectors is not None
        controls.append((action.text_label, node.computed_attributes.selectors.xpath_selector))
    return controls


@pytest.mark.asyncio
async def test_form_controls_named_like_dom_properties_do_not_break_observe() -> None:
    async with NotteSession(headless=True) as session:
        expected = await _observe_form(session, "kids")
        assert [label for label, _ in expected][-1] == "Search"
        for name in CLOBBERING_NAMES:
            assert await _observe_form(session, name) == expected, name


@pytest.mark.asyncio
async def test_a_form_with_a_children_field_can_be_used() -> None:
    async with NotteSession(headless=True) as session:
        _ = await session.window.page.goto(f"data:text/html,{quote(_form('children'))}")
        obs = await session.aobserve()
        search = next(action for action in obs.space.interaction_actions if action.text_label == "Search")

        result = await session.aexecute(type="click", id=search.id)
        assert result.success
        assert await session.window.page.title() == "searched"


DOCUMENT_CLOBBERING = """
    <img name="body"><img name="documentElement"><img name="createRange"><img name="createTreeWalker">
    <img name="elementFromPoint"><img name="styleSheets"><img name="getElementById">
    <span id="label">Search</span><button type="button" aria-labelledby="label">Go</button>
    <p>Some text</p>
    <a href="/next" style="display: block; margin-top: 3000px"><img alt="Next page"></a>
"""


@pytest.mark.asyncio
async def test_named_images_do_not_break_the_dom_build_in_the_page_world() -> None:
    args = {
        "highlight_elements": True,
        "focus_element": -1,
        "viewport_expansion": 0,
        "enable_pointer_elements": True,
    }
    async with NotteSession(headless=True) as session:
        page = session.window.page
        _ = await page.goto(f"data:text/html,{quote(DOCUMENT_CLOBBERING)}")
        # the page's own world: Playwright evaluates there, Patchright in an isolated world unless told otherwise
        world = {"isolated_context": False} if config.browser_backend is BrowserBackend.PATCHRIGHT else {}
        payload = json.loads(await page.evaluate(DOM_TREE_JS, args, **world))

        nodes = payload["map"].values()
        assert payload["map"][payload["rootId"]]["tagName"] == "body"
        buttons = [node for node in nodes if node.get("tagName") == "button"]
        assert [button.get("accessibleName") for button in buttons] == ["Search"]
        assert "Some text" in [node.get("text") for node in nodes]
        links = [node for node in nodes if node.get("tagName") == "a"]
        assert [(link.get("offscreen"), link.get("accessibleName")) for link in links] == [(True, "Next page")]


def _scrolling_form(name: str) -> str:
    return f"""
        <div style="height: 3000px">Top of the page</div>
        <form style="height: 200px; overflow: auto">
          <input type="hidden" name="{name}">
          <div style="height: 400px"></div>
          <button type="button">Search</button>
        </form>
    """


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["kids", "parentElement", "scrollHeight", "children"])
async def test_a_control_below_the_viewport_in_a_form_is_described(name: str) -> None:
    # below the viewport, the walk looks at the form's scroll box to tell whether scrolling can reveal
    # the button: `form.parentElement` made it loop, `form.scrollHeight` judged the button out of reach
    async with NotteSession(headless=True) as session:
        _ = await session.window.page.goto(f"data:text/html,{quote(_scrolling_form(name))}")
        obs = await session.aobserve()

        assert "_[:]<button>Search</button>" in obs.space.description.splitlines()
