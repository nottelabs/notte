"""`observe()` offers a control that something covers in part, not only one shown at its center.

A control was offered when the page's topmost element at its center was the control. A field whose center
is under a banner or a floating panel, with the rest of it in plain sight, was then left out of the
observation without a trace, though it can be typed in. When the center is covered, the part of the
control the covering element leaves is looked at too. A control covered whole stays out.
"""

from urllib.parse import quote

import pytest
from notte_browser.session import NotteSession

PAGE = """
<div style="position: relative">
  <input id="name" placeholder="Name" style="display: block; box-sizing: border-box; height: 30px">
  <input id="email" placeholder="Email" style="display: block; box-sizing: border-box; height: 30px; margin-top: 20px">
  <div style="position: absolute; top: 13px; left: 0; width: 400px; height: 25px; background: #ccc"></div>
  <div style="position: absolute; top: 46px; left: 0; width: 400px; height: 40px; background: #ccc"></div>
</div>
"""


@pytest.mark.asyncio
async def test_a_partly_covered_field_is_offered() -> None:
    """Offer and fill the partly covered field while excluding the fully covered field."""
    async with NotteSession(headless=True) as session:
        _ = await session.window.page.goto(f"data:text/html,{quote(PAGE)}")
        observation = await session.aobserve()

        # the top of the Name field shows above the first panel; the second panel covers the whole Email field
        actions = [(action.id, action.text_label) for action in observation.space.interaction_actions]
        assert actions == [("I1", "Name")]

        _ = await session.aexecute(type="fill", id="I1", value="Jane Doe")
        assert await session.window.page.input_value("#name") == "Jane Doe"


@pytest.mark.asyncio
@pytest.mark.parametrize("clip", ["viewport", "panel", "shadow-panel"])
async def test_clipped_partly_covered_editor_preserves_independent_controls(clip: str) -> None:
    """Probe only the editor's visible part, retaining its descendants' independent click actions."""
    editors = """
    <style>
      .editor { position: absolute; top: 0; width: 300px; height: 500px; }
      .cover { position: absolute; width: 300px; background: #ccc; }
    </style>
    <div class="editor" contenteditable="true">
      <p style="margin: 0">Partial editor</p>
      <span onclick="document.title = 'details'">Details</span>
    </div>
    <button style="position: absolute; top: 4px; left: 220px"
      onclick="document.title = 'saved'">Save</button>
    <div class="editor" contenteditable="true" style="left: 320px"><p>Covered editor</p></div>
    <div class="cover" style="top: 40px; height: 80px"></div>
    <div class="cover" style="left: 320px; top: 0; height: 120px"></div>
    """
    if clip == "viewport":
        # Only 80px of the editor is above the fold; its visible center is covered.
        page = f'<div style="position: relative; top: 400px">{editors}</div>'
    elif clip == "panel":
        page = f'<div style="position: relative; height: 120px; overflow: auto">{editors}</div>'
    else:
        # The clipping panel is outside the editor's shadow root.
        page = f"""<div style="height: 120px; overflow: auto"><editor-host></editor-host></div>
        <template>{editors}</template>
        <script>
          const host = document.querySelector('editor-host');
          host.style = 'display: block; position: relative; height: 500px';
          host.attachShadow({{mode: 'open'}}).append(document.querySelector('template').content.cloneNode(true));
        </script>"""
    async with NotteSession(headless=True, viewport_width=640, viewport_height=480) as session:
        _ = await session.window.page.goto(f"data:text/html,{quote('<style>body { margin: 0 }</style>' + page)}")
        obs = await session.aobserve()
        assert [(action.id, action.type) for action in obs.space.interaction_actions] == [
            ("I1", "fill"),
            ("M1", "click"),
            ("B1", "click"),
        ]
        assert "Partial editor" in obs.space.description

        result = await session.aexecute(type="click", id="M1")
        assert result.success, result.message
        assert await session.window.page.title() == "details"
        result = await session.aexecute(type="click", id="B1")
        assert result.success, result.message
        assert await session.window.page.title() == "saved"
        result = await session.aexecute(type="fill", id="I1", value="Replacement notes")
        assert result.success, result.message
        assert await session.window.page.locator(".editor").first.inner_text() == "Replacement notes"
