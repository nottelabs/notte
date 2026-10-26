"""`observe()` leaves hidden content out of the page description, and keeps what is only off-screen.

Text hidden with `display: none`, `visibility: hidden`, a skipped `content-visibility` (a closed
`<details>`, `hidden="until-found"`) or a zero-height `overflow: hidden` box is not rendered anywhere.
Neither is the text of a fixed panel laid out outside the viewport (a closed off-canvas drawer): scrolling
the page does not bring it in.
On screen, `opacity: 0` and `aria-hidden` hide text too. Below the fold they don't: content waiting to
fade in on scroll has `opacity: 0`, and the visible text next to a control is often `aria-hidden`.
"""

from urllib.parse import quote

import pytest
from notte_browser.session import NotteSession
from notte_core.dom_tree import DomNode
from notte_core.node_type import NodeType

SPACER = '<div style="height: 2000px"></div>'

HIDDEN = """
<h1>Visible heading</h1>
<div style="display: none">DISPLAY_NONE</div>
<div style="visibility: hidden">VISIBILITY_HIDDEN</div>
<div aria-hidden="true">ARIA_HIDDEN</div>
<div style="opacity: 0">OPACITY_ZERO</div>
<div style="height: 0; overflow: hidden"><p>ZERO_HEIGHT</p></div>
<details><summary>Summary</summary>CLOSED_DETAILS</details>
<div hidden="until-found">UNTIL_FOUND</div>
<div hidden="until-found"><span style="display: contents">UNTIL_FOUND_IN_CONTENTS</span></div>
<div style="position: relative; height: 0; overflow: hidden"><span style="position: absolute">CLIPPED_ABSOLUTE</span></div>
<aside style="position: fixed; top: 0; bottom: 0; left: 0; width: 300px; transform: translateX(-110%)" inert>
  <h2>CLOSED_DRAWER</h2><label>CLOSED_DRAWER_LABEL <input type="checkbox"></label>
</aside>
"""

KEPT = (
    """
<h1>Visible heading</h1>
<div style="position: absolute; left: -9999px">OFFSCREEN_LEFT</div>
<span style="position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0)">SCREEN_READER_ONLY</span>
<label>Country <select><option>OPTION_ONE</option><option>OPTION_TWO</option></select></label>
<a href="/next"><span style="display: contents">CONTENTS_LABEL</span></a>
<button><span aria-hidden="true">ICON_TEXT</span></button>
<div style="visibility: hidden"><span style="display: contents; visibility: visible">VISIBLE_IN_HIDDEN</span></div>
<div style="position: relative"><div style="height: 0; overflow: hidden">
  <span style="position: absolute; top: 0">ESCAPES_CLIPPING</span>
</div></div>
<div style="position: fixed; top: 600px; height: 100px; overflow: auto">
  <div style="height: 300px"></div><p>SCROLLED_IN_FIXED_PANEL</p>
</div>
"""
    + SPACER
    + """
<p>BELOW_FOLD</p>
<div style="opacity: 0">FADES_IN_ON_SCROLL</div>
<div aria-hidden="true">ARIA_HIDDEN_BELOW_FOLD</div>
<section style="content-visibility: auto"><p>RENDERED_WHEN_SCROLLED_TO</p></section>
"""
)


async def _observe(markup: str) -> tuple[str, list[DomNode]]:
    async with NotteSession(headless=True, viewport_width=1280, viewport_height=720) as session:
        _ = await session.window.page.goto(f"data:text/html,{quote(markup)}")
        observation = await session.aobserve()
        return observation.space.description, session.snapshot.dom_node.flatten()


@pytest.mark.asyncio
async def test_hidden_text_is_not_in_the_description() -> None:
    description, nodes = await _observe(HIDDEN)

    texts = [node.text for node in nodes if node.type is NodeType.TEXT]
    assert "Visible heading" in description
    for hidden in [
        "DISPLAY_NONE",
        "VISIBILITY_HIDDEN",
        "ARIA_HIDDEN",
        "OPACITY_ZERO",
        "ZERO_HEIGHT",
        "CLOSED_DETAILS",
        "UNTIL_FOUND",
        "UNTIL_FOUND_IN_CONTENTS",
        "CLIPPED_ABSOLUTE",
        "CLOSED_DRAWER",
        "CLOSED_DRAWER_LABEL",
    ]:
        assert hidden not in description
        assert hidden not in texts


@pytest.mark.asyncio
async def test_offscreen_and_labelling_text_is_kept() -> None:
    description, nodes = await _observe(KEPT)

    for kept in [
        "OFFSCREEN_LEFT",
        "SCREEN_READER_ONLY",
        "OPTION_ONE",
        "OPTION_TWO",
        "CONTENTS_LABEL",
        "ICON_TEXT",
        "VISIBLE_IN_HIDDEN",
        "ESCAPES_CLIPPING",
        "SCROLLED_IN_FIXED_PANEL",
        "BELOW_FOLD",
        "FADES_IN_ON_SCROLL",
        "ARIA_HIDDEN_BELOW_FOLD",
        "RENDERED_WHEN_SCROLLED_TO",
    ]:
        assert kept in description
    in_viewport = {node.text: node.computed_attributes.in_viewport for node in nodes if node.type is NodeType.TEXT}
    assert in_viewport["Visible heading"]
    assert not in_viewport["OFFSCREEN_LEFT"]
    assert not in_viewport["BELOW_FOLD"]


@pytest.mark.asyncio
@pytest.mark.parametrize("in_shadow", [False, True])
async def test_closed_drawer_text_across_shadow_roots(in_shadow: bool) -> None:
    markup = """
    <aside id="drawer" style="position: fixed; top: 0; left: 0; width: 300px;
                            height: 500px; transform: translateX(-110%)">
      <drawer-content></drawer-content>
    </aside>
    <script>
      document.querySelector('drawer-content').attachShadow({mode: 'open'}).innerHTML =
        '<p>DRAWER_CONTENT</p>';
    </script>
    """
    if in_shadow:
        markup += """
        <drawer-host></drawer-host>
        <script>
          document.querySelector('drawer-host').attachShadow({mode: 'open'})
            .append(document.getElementById('drawer'));
        </script>
        """
    async with NotteSession(headless=True, viewport_width=1280, viewport_height=720) as session:
        _ = await session.window.page.goto(f"data:text/html,{quote(markup)}")
        assert "DRAWER_CONTENT" not in (await session.aobserve()).space.description
        await session.window.page.locator("#drawer").evaluate("element => element.style.transform = 'none'")
        assert "DRAWER_CONTENT" in (await session.aobserve()).space.description


@pytest.mark.asyncio
@pytest.mark.parametrize("style", ["transform: translateZ(0)", "filter: blur(0px)", "contain: layout"])
@pytest.mark.parametrize("in_shadow", [False, True])
async def test_fixed_text_in_scrolling_containing_block_is_kept(style: str, in_shadow: bool) -> None:
    panel = '<p id="panel" style="position: fixed; top: 0; width: 200px; height: 50px">REACHABLE_FIXED_TEXT</p>'
    if in_shadow:
        panel = f"""
        <fixed-content></fixed-content>
        <script>
          document.querySelector('fixed-content').attachShadow({{mode: 'open'}}).innerHTML = '{panel}';
        </script>
        """
    markup = SPACER + f'<section style="{style}; height: 200px">{panel}</section>'
    async with NotteSession(headless=True, viewport_width=1280, viewport_height=720) as session:
        _ = await session.window.page.goto(f"data:text/html,{quote(markup)}")
        observation = await session.aobserve()
        assert "REACHABLE_FIXED_TEXT" in observation.space.description
        texts = [node for node in session.snapshot.dom_node.flatten() if node.text == "REACHABLE_FIXED_TEXT"]
        assert texts and all(not node.computed_attributes.in_viewport for node in texts)
        await session.window.page.locator("section").scroll_into_view_if_needed()
        observation = await session.aobserve()
        assert "REACHABLE_FIXED_TEXT" in observation.space.description
        texts = [node for node in session.snapshot.dom_node.flatten() if node.text == "REACHABLE_FIXED_TEXT"]
        assert any(node.computed_attributes.in_viewport for node in texts)


@pytest.mark.asyncio
async def test_hidden_controls_are_not_offered() -> None:
    markup = """
    <div style="opacity: 0"><button>FADED_MENU_ITEM</button></div>
    <div style="height: 0; overflow: hidden"><button>COLLAPSED_ITEM</button></div>
    <label style="position: relative">Accept the terms
      <input type="checkbox" style="opacity: 0; position: absolute; inset: 0; width: 100%; height: 100%">
    </label>
    <button aria-hidden="true" tabindex="-1">Next day</button>
    <div style="visibility: hidden"><button style="visibility: visible">Shown in a hidden parent</button></div>
    """
    async with NotteSession(headless=True, viewport_width=1280, viewport_height=720) as session:
        _ = await session.window.page.goto(f"data:text/html,{quote(markup)}")
        _ = await session.aobserve()
        nodes = session.snapshot.interaction_nodes()

    labels = [node.inner_text() for node in nodes]
    assert "FADED_MENU_ITEM" not in labels
    assert "COLLAPSED_ITEM" not in labels
    # a transparent checkbox drawn over by its label is still the control
    assert any(node.attributes is not None and node.attributes.type == "checkbox" for node in nodes)
    # `aria-hidden` does not hide a control the user can see and click
    assert "Next day" in labels
    # `visibility` can be set back to `visible` inside a hidden parent
    assert "Shown in a hidden parent" in labels
