"""`observe()` offers a rich text editor (`contenteditable` without a `role`) as one text field.

Its root used to be a generic clickable (`M1`, a click), and each paragraph inside it another one: they
are editable too, and editors give them a `text` cursor. An editor whose center is below the fold was not
offered at all, only its paragraphs as clickables.
"""

from urllib.parse import quote

import pytest
from notte_browser.dom import parsing
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
async def test_nested_editor_content_does_not_regain_an_action(monkeypatch: pytest.MonkeyPatch) -> None:
    """The highlighted editor stays the only action through nested editable blocks with their own cursor."""
    monkeypatch.setattr(parsing, "config", parsing.config.model_copy(update={"enable_pointer_elements": True}))
    page = """<div class="editor" contenteditable="true">
      <section style="cursor: auto"><p style="cursor: text">Nested text</p></section>
    </div>"""
    async with NotteSession(headless=True) as session:
        _ = await session.window.page.goto(f"data:text/html,{quote(page)}")
        frame = await parsing.parse_frames(session.window.page)
        assert [node.get("tagName") for node in frame.nodes.values() if "highlightIndex" in node] == ["div"]
        obs = await session.aobserve()

        assert [(action.id, action.type) for action in obs.space.interaction_actions] == [("I1", "fill")]
        assert "Nested text" in obs.space.description


@pytest.mark.asyncio
@pytest.mark.parametrize("editable", ["", "true", "plaintext-only"])
async def test_nested_editable_click_handler_keeps_its_click_action(editable: str) -> None:
    """An editable descendant with its own handler remains clickable beside the fillable editor."""
    page = f"""<div class="editor" contenteditable="true">
      <p>Notes</p><span contenteditable="{editable}"
        onclick="document.body.dataset.clicked = 'yes'">Open details</span>
    </div>"""
    async with NotteSession(headless=True) as session:
        _ = await session.window.page.goto(f"data:text/html,{quote(page)}")
        obs = await session.aobserve()
        assert [(action.id, action.type) for action in obs.space.interaction_actions] == [
            ("I1", "fill"),
            ("M1", "click"),
        ]
        result = await session.aexecute(type="click", id="M1")
        assert result.success, result.message
        assert await session.window.page.locator("body").get_attribute("data-clicked") == "yes"
        result = await session.aexecute(type="fill", id="I1", value="Replacement notes")
        assert result.success, result.message
        assert await session.window.page.locator(".editor").inner_text() == "Replacement notes"


@pytest.mark.asyncio
async def test_contenteditable_cut_by_the_viewport_is_a_field_in_view() -> None:
    async with NotteSession(headless=True) as session:
        _ = await session.window.page.goto(f"data:text/html,{quote(CUT_SPACER + EDITOR)}")
        obs = await session.aobserve()

        assert [(action.id, action.type) for action in obs.space.interaction_actions] == [("I1", "fill")]

        result = await session.aexecute(type="fill", id="I1", value="Clipped replacement")
        assert result.success, result.message
        assert await session.window.page.locator(".editor").inner_text() == "Clipped replacement"


@pytest.mark.asyncio
async def test_contenteditable_cut_by_a_scrolling_panel_is_a_field_in_view() -> None:
    # the editor's center is in the viewport but below the panel's visible part
    page = f'<div style="height: 150px; overflow: auto">{EDITOR.replace("height: 400px", "height: 500px")}</div>'
    async with NotteSession(headless=True) as session:
        _ = await session.window.page.goto(f"data:text/html,{quote(page)}")
        obs = await session.aobserve()

        assert [(action.id, action.type) for action in obs.space.interaction_actions] == [("I1", "fill")]

        result = await session.aexecute(type="fill", id="I1", value="Clipped replacement")
        assert result.success, result.message
        assert await session.window.page.locator(".editor").inner_text() == "Clipped replacement"


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


@pytest.mark.asyncio
@pytest.mark.parametrize("shadow", [False, True])
@pytest.mark.parametrize("scale", [1, 2])
async def test_clipped_editor_uses_the_scroll_box_inner_bounds(shadow: bool, scale: int) -> None:
    """A visible slice stays fillable across scaled borders and shadow hosts, until scrolled away."""
    contents = """<div style="height:70px"></div>
      <div class="editor" contenteditable="true" style="height:300px;width:220px">
        <span onclick="this.dataset.clicked = 'yes'">Open details</span><p>Notes</p>
      </div><div style="height:300px"></div>"""
    page = f"""<div id="box" style="height:100px;width:260px;overflow:auto;border:20px solid;
      transform:scale({scale});transform-origin:top left">{"" if shadow else contents}</div>"""
    async with NotteSession(headless=True, viewport_width=1280, viewport_height=720) as session:
        _ = await session.window.page.goto(f"data:text/html,{quote(page)}")
        if shadow:
            _ = await session.window.page.locator("#box").evaluate(
                "(box, contents) => { box.attachShadow({mode: 'open'}).innerHTML = contents; }", contents
            )
        editor = session.window.page.locator(".editor")
        assert await editor.evaluate("""element => {
            const box = document.getElementById('box');
            const rect = box.getBoundingClientRect();
            const scale = rect.height / box.offsetHeight;
            const own = element.getBoundingClientRect();
            const y = (own.top + rect.top + (box.clientTop + box.clientHeight) * scale) / 2;
            return element.contains(element.getRootNode().elementFromPoint(own.left + 10, y));
        }""")
        obs = await session.aobserve()
        assert [(action.id, action.type) for action in obs.space.interaction_actions] == [
            ("I1", "fill"),
            ("M1", "click"),
        ]
        result = await session.aexecute(type="click", id="M1")
        assert result.success, result.message
        assert await editor.locator("span").get_attribute("data-clicked") == "yes"
        result = await session.aexecute(type="fill", id="I1", value="Visible notes")
        assert result.success, result.message
        assert await editor.inner_text() == "Visible notes"

        _ = await session.window.page.locator("#box").evaluate("box => { box.scrollTop = 400; }")
        obs = await session.aobserve()
        assert obs.space.interaction_actions == []
        assert "_[:]<div>Visible notes</div>" in obs.space.description

        _ = await session.window.page.locator("#box").evaluate("box => { box.scrollTop = 100; }")
        obs = await session.aobserve()
        assert [(action.id, action.type) for action in obs.space.interaction_actions] == [("I1", "fill")]
        result = await session.aexecute(type="fill", id="I1", value="Scrolled notes")
        assert result.success, result.message
        assert await editor.inner_text() == "Scrolled notes"


@pytest.mark.asyncio
@pytest.mark.parametrize("position", ["fixed", "absolute"])
@pytest.mark.parametrize("transform", [False, True])
async def test_editor_in_a_popup_obeys_its_containing_block(position: str, transform: bool) -> None:
    page = f"""<div style="position:relative">
      <div id="box" style="height:100px;width:300px;overflow:auto;
        transform:{"translateZ(0)" if transform else "none"}">
        <div style="height:400px"></div>
        <div style="position:{position};top:150px;left:20px">
          <div class="editor" contenteditable="true" style="width:200px;height:80px">Popup notes</div>
        </div>
      </div></div>"""
    async with NotteSession(headless=True, viewport_width=1280, viewport_height=720) as session:
        _ = await session.window.page.goto(f"data:text/html,{quote(page)}")
        editor = session.window.page.locator(".editor")
        assert await editor.evaluate("""element => {
            const rect = element.getBoundingClientRect();
            return document.elementFromPoint(rect.x + rect.width / 2, rect.y + rect.height / 2) === element;
        }""") is (not transform)
        obs = await session.aobserve()
        if transform:
            assert obs.space.interaction_actions == []
            assert "_[:]<div>Popup notes</div>" in obs.space.description
            _ = await session.window.page.locator("#box").evaluate("box => { box.scrollTop = 120; }")
            obs = await session.aobserve()
        assert [(action.id, action.type) for action in obs.space.interaction_actions] == [("I1", "fill")]
        result = await session.aexecute(type="fill", id="I1", value="Popup replacement")
        assert result.success, result.message
        assert await editor.inner_text() == "Popup replacement"


@pytest.mark.asyncio
@pytest.mark.parametrize("position", ["fixed", "absolute"])
async def test_escaping_editor_is_hit_tested_beyond_the_scroll_box(position: str) -> None:
    page = f"""<div style="position:relative">
      <div style="height:100px;width:300px;overflow:auto">
        <div style="height:400px"></div>
        <div style="position:{position};top:80px;left:20px">
          <div class="editor" contenteditable="true" style="width:200px;height:300px">Popup notes</div>
        </div>
      </div></div>
      <div id="cover" style="position:fixed;top:0;left:0;width:400px;height:120px;z-index:10"></div>"""
    async with NotteSession(headless=True, viewport_width=1280, viewport_height=720) as session:
        _ = await session.window.page.goto(f"data:text/html,{quote(page)}")
        editor = session.window.page.locator(".editor")
        assert await editor.evaluate("""element => {
            const rect = element.getBoundingClientRect();
            return document.elementFromPoint(rect.x + rect.width / 2, rect.y + rect.height / 2) === element;
        }""")
        obs = await session.aobserve()
        assert [(action.id, action.type) for action in obs.space.interaction_actions] == [("I1", "fill")]
        result = await session.aexecute(type="fill", id="I1", value="Escaped notes")
        assert result.success, result.message
        assert await editor.inner_text() == "Escaped notes"

        _ = await session.window.page.locator("#cover").evaluate("cover => { cover.style.height = '500px'; }")
        obs = await session.aobserve()
        assert obs.space.interaction_actions == []
