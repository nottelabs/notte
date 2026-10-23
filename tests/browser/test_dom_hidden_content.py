"""`observe()` leaves hidden content out of the page description, and keeps what is only off-screen.

Text hidden with `display: none`, `visibility: hidden`, a skipped `content-visibility` (a closed
`<details>`, `hidden="until-found"`) or a zero-height `overflow: hidden` box is not rendered anywhere.
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
"""

KEPT = (
    """
<h1>Visible heading</h1>
<div style="position: absolute; left: -9999px">OFFSCREEN_LEFT</div>
<span style="position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0)">SCREEN_READER_ONLY</span>
<label>Country <select><option>OPTION_ONE</option><option>OPTION_TWO</option></select></label>
<a href="/next"><span style="display: contents">CONTENTS_LABEL</span></a>
<button><span aria-hidden="true">ICON_TEXT</span></button>
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
async def test_hidden_controls_are_not_offered() -> None:
    markup = """
    <div style="opacity: 0"><button>FADED_MENU_ITEM</button></div>
    <div style="height: 0; overflow: hidden"><button>COLLAPSED_ITEM</button></div>
    <label style="position: relative">Accept the terms
      <input type="checkbox" style="opacity: 0; position: absolute; inset: 0; width: 100%; height: 100%">
    </label>
    <button aria-hidden="true" tabindex="-1">Next day</button>
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
