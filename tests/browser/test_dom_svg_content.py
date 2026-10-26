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
async def test_svg_shape_with_assigned_click_handler_is_observed_in_the_page_world() -> None:
    """A chart's assigned handler makes its bar actionable where the handler lives."""
    page = """<svg width="200" height="100">
<rect width="100" height="80" aria-label="March: 1250 sign-ups"/><text x="0" y="98">March</text>
</svg><script>document.querySelector('rect').onclick = () => { document.title = 'March'; };</script>"""
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
async def test_svg_icon_stays_out_of_the_tree() -> None:
    async with NotteSession(headless=True) as session:
        _ = await session.window.page.goto(f"data:text/html,{quote(ICON_BUTTON)}")
        obs = await session.aobserve()

        tags = {node.attributes.tag_name for node in session.snapshot.dom_node.flatten() if node.attributes}
        assert "svg" not in tags
        assert "path" not in tags
        assert [(action.id, action.text_label) for action in obs.space.interaction_actions] == [("B1", "Search")]
