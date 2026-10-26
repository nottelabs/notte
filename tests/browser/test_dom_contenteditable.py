"""`observe()` offers a rich text editor (`contenteditable` without a `role`) as one text field.

Its root used to be a generic clickable (`M1`, a click), and each paragraph inside it another one: they
are editable too, and editors give them a `text` cursor. An editor whose center is below the fold was not
offered at all, only its paragraphs as clickables.
"""

from urllib.parse import quote

import pytest
from notte_browser.session import NotteSession

EDITOR = """
<style>.editor > * { cursor: text; }</style>
<h2>Notes</h2>
<div class="editor" contenteditable="true" style="height: 400px"><h1>Title</h1><p>Body</p><p>Second line</p></div>
"""

# the editor's center is below the viewport, its first paragraphs are in it
CUT_SPACER = '<div style="height: calc(100vh - 100px)">Top of the page</div>'
# the whole editor is below the viewport
BELOW_SPACER = '<div style="height: 120vh">Top of the page</div>'


@pytest.mark.asyncio
async def test_contenteditable_root_is_one_text_field() -> None:
    async with NotteSession(headless=True) as session:
        _ = await session.window.page.goto(f"data:text/html,{quote(EDITOR)}")
        obs = await session.aobserve()

        assert [(action.id, action.type) for action in obs.space.interaction_actions] == [("I1", "fill")]
        assert "I1[:]<div>Title\nBody\nSecond line</div>" in obs.space.description

        result = await session.aexecute(type="fill", id="I1", value="New text")
        assert result.success, result.message
        assert await session.window.page.locator(".editor").inner_text() == "New text"


@pytest.mark.asyncio
async def test_contenteditable_cut_by_the_viewport_is_a_field_in_view() -> None:
    async with NotteSession(headless=True) as session:
        _ = await session.window.page.goto(f"data:text/html,{quote(CUT_SPACER + EDITOR)}")
        obs = await session.aobserve()

        assert [(action.id, action.type) for action in obs.space.interaction_actions] == [("I1", "fill")]


@pytest.mark.asyncio
async def test_contenteditable_cut_by_a_scrolling_panel_is_a_field_in_view() -> None:
    # the editor's center is in the viewport but below the panel's visible part
    page = f'<div style="height: 150px; overflow: auto">{EDITOR.replace("height: 400px", "height: 500px")}</div>'
    async with NotteSession(headless=True) as session:
        _ = await session.window.page.goto(f"data:text/html,{quote(page)}")
        obs = await session.aobserve()

        assert [(action.id, action.type) for action in obs.space.interaction_actions] == [("I1", "fill")]


@pytest.mark.asyncio
async def test_contenteditable_below_the_fold_is_an_offscreen_field() -> None:
    async with NotteSession(headless=True) as session:
        _ = await session.window.page.goto(f"data:text/html,{quote(BELOW_SPACER + EDITOR)}")
        obs = await session.aobserve()

        # described without an action until it is scrolled to, and its paragraphs are not clickables
        assert obs.space.interaction_actions == []
        assert "_[:]<div>Title\nBody\nSecond line</div>" in obs.space.description

        _ = await session.window.page.locator(".editor").scroll_into_view_if_needed()
        obs = await session.aobserve()
        assert [(action.id, action.type) for action in obs.space.interaction_actions] == [("I1", "fill")]


# the iframe of an editor, whose `<body>` is the editing host (as TinyMCE's is)
EDITOR_FRAME = """<h2>Message</h2><iframe style="width: 600px; height: 300px" srcdoc='<body contenteditable="true">
<p>Hello <strong>bold</strong></p><p>World</p></body>'></iframe>"""


@pytest.mark.asyncio
async def test_blocks_of_an_editable_body_stay_offered() -> None:
    # the `<body>` is never highlighted: the blocks right inside it are offered, the formatting inside them is not
    async with NotteSession(headless=True) as session:
        _ = await session.window.page.goto(f"data:text/html,{quote(EDITOR_FRAME)}")
        obs = await session.aobserve()

        actions = [(action.id, action.text_label) for action in obs.space.interaction_actions]
        assert actions == [("M1", "Hello bold"), ("M2", "World")]
