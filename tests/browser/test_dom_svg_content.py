"""`observe()` describes the links and text of an `<svg>` chart, and still leaves icons out.

The DOM build used to drop every `<svg>` with its subtree, so a bar chart whose bars are links
(`<a href aria-label="March: 1,250">`) offered no action, and its axis labels (`<text>`) were not in
the description. SVG elements have no `offsetWidth` either, which made them count as invisible.
"""

import json
from urllib.parse import quote

import pytest
from notte_browser.dom.parsing import DOM_TREE_JS
from notte_browser.session import NotteSession

CHART = """
<h2>Monthly sign-ups</h2>
<svg width="400" height="260" role="img" aria-labelledby="chart-title">
  <title id="chart-title">Monthly sign-ups</title>
  <g>
    <text x="0" y="30">1000</text>
    <a href="#month-1" aria-label="January: 820 sign-ups">
      <rect x="50" y="66" width="40" height="164"><title>January: 820</title></rect>
    </a>
    <text x="58" y="248">Jan</text>
    <a href="#month-2" aria-label="February: 910 sign-ups">
      <rect x="112" y="48" width="40" height="182"><title>February: 910</title></rect>
    </a>
    <text x="120" y="248">Feb</text>
  </g>
</svg>
<script>
  // the click is recorded: a data: URL does not navigate to a fragment
  document.addEventListener("click", (event) => { document.title = event.target.closest("a")?.getAttribute("href") ?? ""; });
</script>
"""

ICON_BUTTON = """
<button><svg width="16" height="16" viewBox="0 0 16 16"><path d="M1 1h14v14H1z"/></svg>Search</button>
"""


@pytest.mark.asyncio
async def test_svg_chart_links_and_labels_are_observed() -> None:
    async with NotteSession(headless=True) as session:
        _ = await session.window.page.goto(f"data:text/html,{quote(CHART)}")
        obs = await session.aobserve()

        links = {action.id: action.accessible_name for action in obs.space.interaction_actions}
        assert links == {"L1": "January: 820 sign-ups", "L2": "February: 910 sign-ups"}
        description = obs.space.description
        for label in ("1000", "Jan", "Feb"):
            assert f"_[:]{label}\n" in description + "\n"
        # the tooltips are not rendered text
        assert "January: 820\n" not in description + "\n"

        result = await session.aexecute(type="click", id="L2")
        assert result.success, result.message
        assert await session.window.page.title() == "#month-2"


@pytest.mark.asyncio
async def test_svg_chart_below_the_fold_keeps_its_labels() -> None:
    async with NotteSession(headless=True, viewport_width=1280, viewport_height=720) as session:
        page = f'<div style="height: 1500px">Intro</div>{CHART}'
        _ = await session.window.page.goto(f"data:text/html,{quote(page)}")
        obs = await session.aobserve()

        description = obs.space.description + "\n"
        for label in ("1000", "Jan", "Feb"):
            assert f"_[:]{label}\n" in description


@pytest.mark.asyncio
async def test_svg_with_html_controls_keeps_them() -> None:
    page = """<svg width="200" height="60"><foreignObject x="0" y="0" width="200" height="60">
<button>Apply</button><input aria-label="Zoom"></foreignObject></svg>"""
    async with NotteSession(headless=True) as session:
        _ = await session.window.page.goto(f"data:text/html,{quote(page)}")
        obs = await session.aobserve()

        offered = {(action.id, action.text_label or action.accessible_name) for action in obs.space.interaction_actions}
        assert offered == {("B1", "Apply"), ("I1", "Zoom")}


@pytest.mark.asyncio
@pytest.mark.parametrize("link_attribute", ["href", "xlink:href"])
async def test_svg_link_without_text_is_observed_and_clickable(link_attribute: str) -> None:
    """Both SVG link attributes keep a shape-only linked chart in the tree."""
    page = f"""<svg width="200" height="100" xmlns:xlink="http://www.w3.org/1999/xlink">
<a {link_attribute}="#month" aria-label="March: 1250 sign-ups"><rect width="100" height="80"/></a>
</svg><script>
document.querySelector('a').addEventListener('click', () => {{ document.title = 'March'; }});
</script>"""
    async with NotteSession(headless=True) as session:
        _ = await session.window.page.goto(f"data:text/html,{quote(page)}")
        obs = await session.aobserve()

        actions = obs.space.interaction_actions
        assert len(actions) == 1
        assert actions[0].accessible_name == "March: 1250 sign-ups"
        result = await session.aexecute(type="click", id=actions[0].id)
        assert result.success, result.message
        assert await session.window.page.title() == "March"


@pytest.mark.asyncio
@pytest.mark.parametrize("label", ['<text x="0" y="98">March</text>', ""])
async def test_svg_shape_with_assigned_click_handler_is_observed_in_the_page_world(label: str) -> None:
    """A chart's assigned handler makes its bar actionable where the handler lives."""
    page = f"""<svg width="200" height="100">
<rect width="100" height="80" aria-label="March: 1250 sign-ups"/>{label}
</svg><script>document.querySelector('rect').onclick = () => {{ document.title = 'March'; }};</script>"""
    async with NotteSession(headless=True) as session:
        browser_page = session.window.page
        _ = await browser_page.goto(f"data:text/html,{quote(page)}")
        args = {
            "highlight_elements": True,
            "focus_element": -1,
            "viewport_expansion": 0,
            "enable_pointer_elements": True,
        }
        payload = json.loads(await browser_page.evaluate(DOM_TREE_JS, args, isolated_context=False))
        shapes = [node for node in payload["map"].values() if node.get("tagName") == "rect"]
        assert len(shapes) == 1
        assert shapes[0].get("highlightIndex") is not None
        assert shapes[0].get("accessibleName") == "March: 1250 sign-ups"
        await browser_page.locator("rect").click()
        assert await browser_page.title() == "March"


@pytest.mark.asyncio
async def test_shape_only_svg_with_a_click_handler_attribute_is_observed_and_clickable() -> None:
    """The `<svg>` itself handles the click: it is kept, though it has no text or link."""
    page = """<svg width="100" height="100" aria-label="Close" onclick="document.title = 'closed'">
<path d="M10 10L90 90M90 10L10 90" stroke="black" stroke-width="8"/></svg>"""
    async with NotteSession(headless=True) as session:
        _ = await session.window.page.goto(f"data:text/html,{quote(page)}")
        obs = await session.aobserve()

        actions = obs.space.interaction_actions
        assert [action.accessible_name for action in actions] == ["Close"]
        result = await session.aexecute(type="click", id=actions[0].id)
        assert result.success, result.message
        assert await session.window.page.title() == "closed"


@pytest.mark.asyncio
async def test_shape_only_svg_with_an_assigned_click_handler_is_observed_in_the_page_world() -> None:
    page = """<svg width="100" height="100" aria-label="Close">
<path d="M10 10L90 90M90 10L10 90" stroke="black" stroke-width="8"/></svg>
<script>document.querySelector('svg').onclick = () => { document.title = 'closed'; };</script>"""
    async with NotteSession(headless=True) as session:
        browser_page = session.window.page
        _ = await browser_page.goto(f"data:text/html,{quote(page)}")
        args = {
            "highlight_elements": True,
            "focus_element": -1,
            "viewport_expansion": 0,
            "enable_pointer_elements": True,
        }
        payload = json.loads(await browser_page.evaluate(DOM_TREE_JS, args, isolated_context=False))
        roots = [node for node in payload["map"].values() if node.get("tagName") == "svg"]
        assert len(roots) == 1
        assert roots[0].get("highlightIndex") is not None
        assert roots[0].get("accessibleName") == "Close"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("content", "selector", "property_name", "expected_tag", "expected_name"),
    [
        ('<text x="0" y="30">March</text>', "svg", "querySelectorAll", "text", "March"),
        ('<text x="0" y="30">March</text>', "text", "textContent", "text", "March"),
        (
            '<foreignObject width="200" height="60"><input aria-label="Zoom"></foreignObject>',
            "foreignObject",
            "firstElementChild",
            "input",
            "Zoom",
        ),
    ],
)
async def test_svg_content_scan_uses_native_dom_reads(
    content: str, selector: str, property_name: str, expected_tag: str, expected_name: str
) -> None:
    """Page-world property overrides cannot hide chart text or controls."""
    page = f'<svg width="200" height="100">{content}</svg>'
    async with NotteSession(headless=True) as session:
        browser_page = session.window.page
        _ = await browser_page.goto(f"data:text/html,{quote(page)}")
        await browser_page.evaluate(
            """({selector, name}) => {
                Object.defineProperty(document.querySelector(selector), name, {
                    get() { throw new Error('Page-owned property must not be read'); }
                });
            }""",
            {"selector": selector, "name": property_name},
            isolated_context=False,
        )
        payload = json.loads(
            await browser_page.evaluate(
                DOM_TREE_JS,
                {
                    "highlight_elements": True,
                    "focus_element": -1,
                    "viewport_expansion": 0,
                    "enable_pointer_elements": True,
                },
                isolated_context=False,
            )
        )
        nodes = [node for node in payload["map"].values() if node.get("tagName") == expected_tag]
        assert len(nodes) == 1
        if expected_tag == "input":
            assert nodes[0].get("accessibleName") == expected_name
            assert nodes[0].get("highlightIndex") is not None
        else:
            assert expected_name in [node.get("text") for node in payload["map"].values()]


@pytest.mark.asyncio
async def test_svg_icon_stays_out_of_the_tree() -> None:
    async with NotteSession(headless=True) as session:
        _ = await session.window.page.goto(f"data:text/html,{quote(ICON_BUTTON)}")
        obs = await session.aobserve()

        tags = {node.attributes.tag_name for node in session.snapshot.dom_node.flatten() if node.attributes}
        assert "svg" not in tags
        assert "path" not in tags
        assert [(action.id, action.text_label) for action in obs.space.interaction_actions] == [("B1", "Search")]
