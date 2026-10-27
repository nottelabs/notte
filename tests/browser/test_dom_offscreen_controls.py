"""`observe()` describes the controls above and below the viewport without offering them as actions.

Only the elements in the viewport get an id, while the description covers the whole page. A link below the
fold used to be rendered as its text alone, and a field below the fold not at all, so a caller reading the
description could not tell that the page links somewhere or has a field further down. They are now rendered
like the controls in view, without an id and with fewer attributes, and their nodes are marked
`DomNode.offscreen`. Hidden controls stay out, as their text does.
"""

import json
from urllib.parse import quote

import pytest
from notte_browser.dom.parsing import DOM_TREE_JS
from notte_browser.session import NotteSession

PAGE = """
<h1>Alan Turing</h1>
<a href="/wiki/Mathematician" title="Mathematician">Top link</a>
<div style="height: 2000px"></div>
<p>He worked at <a href="/wiki/Bletchley_Park" title="Bletchley Park">Bletchley Park</a> during the war.</p>
<button type="button">Show more</button>
<input type="email" placeholder="Email">
<button disabled>Subscribe</button>
<a href="#cite" style="display: inline-block; width: 12px; height: 12px"></a>
<a href="/home"><img alt="Home" width="20" height="20" src="data:image/gif;base64,R0lGODlhAQABAAAAACw="></a>
<div style="height: 40px; overflow: hidden"><div style="height: 100px"></div><button>CLIPPED_AWAY</button></div>
<div style="height: 40px; overflow: auto"><div style="height: 100px"></div><button>Scrolled to in its box</button></div>
<div style="height: 40px; overflow: hidden"><div style="height: 40px; overflow: auto">
  <div style="height: 100px"></div><button>Scrolled to in a clipped box</button>
</div></div>
<div style="display: none"><a href="/a">DISPLAY_NONE</a></div>
<div style="visibility: hidden"><a href="/b">VISIBILITY_HIDDEN</a></div>
<div style="height: 0; overflow: hidden"><a href="/c">ZERO_HEIGHT</a></div>
<details><summary>Notes</summary><a href="/d">CLOSED_DETAILS</a></details>
<div hidden="until-found"><a href="/e">UNTIL_FOUND</a></div>
<a href="/f" style="position: absolute; left: -9999px; top: 2100px">LEFT_OF_VIEWPORT</a>
<div style="height: 400px"></div>
"""

BELOW = [
    "_[:]He worked at",
    "_[:]<a>Bletchley Park</a>",
    "_[:]during the war.",
    "_[:]<button>Show more</button>",
    '_[:]<input type="email" placeholder="Email"></input>',
    "_[:]<button disabled>Subscribe</button>",
    # named by its image
    "_[:]<a>Home</a>",
    # clipped away by a box that does not scroll: what scrolling cannot reveal stays text
    "_[:]CLIPPED_AWAY",
    "_[:]<button>Scrolled to in its box</button>",
    "_[:]<button>Scrolled to in a clipped box</button>",
    # a generic clickable (a `<summary>`) is not described as a control off-screen
    "_[:]Notes",
    "_[:]LEFT_OF_VIEWPORT",
]


async def _observe(session: NotteSession) -> tuple[list[str], list[tuple[str, str]]]:
    obs = await session.aobserve()
    lines = obs.space.description.splitlines()[1:]
    return lines, [(action.id, action.text_label) for action in obs.space.interaction_actions]


@pytest.mark.asyncio
async def test_nested_scroller_observation_does_not_repeat_escape_ancestor_walks() -> None:
    """Doubling controls and scroll depth costs quadratic work, rather than cubic work."""
    measured_script = (
        DOM_TREE_JS.replace("let highlightIndex = 0;", "let ancestorReads = 0; let highlightIndex = 0;")
        .replace(
            "function composedParentElement(element) {",
            "function composedParentElement(element) { ancestorReads++;",
        )
        .replace(
            "JSON.stringify({ rootId, map: DOM_HASH_MAP })",
            "JSON.stringify({ rootId, map: DOM_HASH_MAP, ancestorReads })",
        )
    )
    work: list[int] = []
    async with NotteSession(headless=True, viewport_width=1280, viewport_height=720) as session:
        for size in (40, 80):
            await session.window.page.goto(
                "data:text/html,<style>"
                ".scroll{height:220px;width:400px;overflow:auto}"
                "button{display:inline-block;width:4px;box-sizing:border-box;height:20px;padding:0;font-size:1px}"
                "</style>"
            )
            await session.window.page.evaluate(
                """size => {
                let parent = document.body;
                for (let i = 0; i < size; i++) {
                    const box = document.createElement('div');
                    box.className = 'scroll';
                    const spacer = document.createElement('div');
                    spacer.style.height = '240px';
                    parent.prepend(box);
                    box.append(spacer);
                    parent = box;
                }
                for (let i = 0; i < size; i++) {
                    const button = document.createElement('button');
                    button.textContent = `Choice ${i}`;
                    parent.insertBefore(button, parent.lastChild);
                }
                const later = document.createElement('button');
                later.textContent = 'Later';
                parent.append(later);
            }""",
                size,
            )
            payload = json.loads(
                await session.window.page.evaluate(
                    measured_script,
                    {
                        "highlight_elements": False,
                        "focus_element": -1,
                        "viewport_expansion": 0,
                        "enable_pointer_elements": False,
                    },
                )
            )
            work.append(payload["ancestorReads"])
            obs = await session.aobserve()
            assert "Choice 0" in [action.text_label for action in obs.space.interaction_actions]
            assert "_[:]<button>Later</button>" in obs.space.description
        assert work[1] <= 5 * work[0], work


@pytest.mark.asyncio
async def test_controls_outside_the_viewport_are_described_without_actions() -> None:
    async with NotteSession(headless=True, viewport_width=1280, viewport_height=720) as session:
        _ = await session.window.page.goto(f"data:text/html,{quote(PAGE)}")
        lines, actions = await _observe(session)

        # hidden controls are left out, a nameless link says nothing, and what is left of the viewport is not
        # reached by scrolling: it stays text
        assert lines == [
            "_[:]Alan Turing",
            'L1[:]<a href="/wiki/Mathematician" title="Mathematician">Top link</a>',
            *BELOW,
        ]
        assert actions == [("L1", "Top link")]
        offscreen = [node for node in session.snapshot.dom_node.flatten() if node.offscreen]
        assert [(node.id, node.get_role_str(), node.inner_text()) for node in offscreen] == [
            (None, "link", "Bletchley Park"),
            (None, "button", "Show more"),
            (None, "textbox", "Email"),
            (None, "link", ""),
            (None, "link", ""),
            (None, "button", "Scrolled to in its box"),
            (None, "button", "Scrolled to in a clipped box"),
        ]

        # scrolled into view, they are actions like any other, and the link now above the viewport is described
        _ = await session.window.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        lines, actions = await _observe(session)
        assert lines[:2] == ["_[:]Alan Turing", "_[:]<a>Top link</a>"]
        assert '_[:]<a href="/wiki/Bletchley_Park" title="Bletchley Park">Bletchley Park</a>' not in lines
        assert 'L1[:]<a href="/wiki/Bletchley_Park" title="Bletchley Park">Bletchley Park</a>' in lines
        assert [action_id for action_id, _ in actions] == ["L1", "B1", "I1", "L2", "L3", "M1", "M2"]


REACH = """
<h1>Top</h1>
<div style="height: 2000px"></div>
<button title="" style="width: 20px; height: 20px"></button>
<a href="/home"><svg width="20" height="20"><title>Home</title><rect width="20" height="20"></rect></svg></a>
<button style="position: fixed; top: 1500px; left: 10px">FIXED_BELOW</button>
<div style="position: fixed; top: 1500px; left: 200px"><a href="/panel">IN_FIXED_PANEL</a></div>
<div style="position: sticky; top: 0"><a href="/section">Sticky section link</a></div>
<div style="position: fixed; top: 0; right: 0; width: 300px; height: 300px; overflow: auto">
  <button style="position: relative; top: -100px">ABOVE_THE_PANEL_START</button>
  <div style="height: 2000px"></div><button>In a fixed scrollable panel</button><input placeholder="Panel field">
</div>
<div style="position: relative">
  <div style="height: 40px; overflow: hidden">
    <div style="position: absolute; top: 60px; height: 40px; overflow: auto">
      <div style="height: 100px"></div><button>In a scrollable box that escapes its clipping</button>
    </div>
  </div>
</div>
<div style="width: 50px; overflow: hidden"><div style="width: 300px; height: 40px; overflow: auto">
  <div style="height: 100px"></div><button style="margin-left: 150px">BESIDE</button>
</div></div>
<div style="height: 400px"></div>
"""


@pytest.mark.asyncio
async def test_only_controls_that_scrolling_reaches_are_described() -> None:
    async with NotteSession(headless=True, viewport_width=1280, viewport_height=720) as session:
        _ = await session.window.page.goto(f"data:text/html,{quote(REACH)}")
        lines, _ = await _observe(session)

        assert lines == [
            "_[:]Top",
            # an empty `title` names nothing: the button says nothing and is left out
            # an SVG icon's `<title>` is not in the description: the link is named by it
            "_[:]<a>Home</a>",
            # page scrolling does not move fixed content: outside the viewport, it is never seen
            # sticky content scrolls with the page until it sticks
            "_[:]<a>Sticky section link</a>",
            # a fixed panel on screen scrolls to what it holds, but not to what is above where its scrolling starts
            "_[:]ABOVE_THE_PANEL_START",
            "_[:]<button>In a fixed scrollable panel</button>",
            '_[:]<input placeholder="Panel field"></input>',
            # its scrollable box escapes the clipping box (positioned outside it), and scrolls down to it
            "_[:]<button>In a scrollable box that escapes its clipping</button>",
            # its box scrolls down, not sideways: it stays out of the clipping box's width
            "_[:]BESIDE",
        ]

        # the sticky link is in view once scrolled to; the fixed ones never are
        _ = await session.window.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        _, actions = await _observe(session)
        assert ("L2", "Sticky section link") in actions
        assert all(label not in ("FIXED_BELOW", "IN_FIXED_PANEL") for _, label in actions)


FOLD = """
<button style="position: absolute; top: 650px; left: 10px; height: 60px">Center in view</button>
<button style="position: absolute; top: 700px; left: 300px; height: 60px">Center below the fold</button>
<div style="height: 2000px"></div>
"""


@pytest.mark.asyncio
async def test_a_control_cut_by_the_edge_of_the_viewport_is_in_one_list() -> None:
    # a control is in view when its center is (where `isTopElement` looks for it), else described off-screen:
    # one cut by the bottom edge is either offered or described, whatever the platform's text metrics
    async with NotteSession(headless=True, viewport_width=1280, viewport_height=720) as session:
        _ = await session.window.page.goto(f"data:text/html,{quote(FOLD)}")
        lines, actions = await _observe(session)
        assert lines == ["B1[:]<button>Center in view</button>", "_[:]<button>Center below the fold</button>"]
        assert actions == [("B1", "Center in view")]


SCROLL_BOXES = """
<div style="height: 300px; overflow: auto; transform: scale(2); transform-origin: top left; width: 200px">
  <div style="height: 2000px"></div><button>Scaled</button>
</div>
<div style="height: 300px; overflow: auto; display: flex; flex-direction: column-reverse; width: 300px; margin-top: 400px">
  <button>Newest</button><div style="flex: none; height: 2000px"></div><button>Older</button>
</div>
<div dir="rtl" style="height: 300px; width: 300px; overflow: auto">
  <div style="width: 1000px; height: 2000px"></div>
  <div style="width: 1000px"><button>Far left</button></div>
  <button style="position: relative; left: 400px">RTL_PAST_ITS_START</button>
</div>
<div style="position: fixed; top: 0; left: 900px; width: 300px; height: 300px; overflow: auto">
  <div style="height: 2000px"></div><button style="position: relative; left: -500px">SHIFTED_OUT_OF_ITS_PANEL</button>
</div>
<div style="display: contents; overflow: auto"><input placeholder="In a box without a box"></div>
<div style="height: 3000px"></div>
"""


@pytest.mark.asyncio
async def test_scrollable_boxes_reach_the_area_they_scroll_through() -> None:
    async with NotteSession(headless=True, viewport_width=1280, viewport_height=720) as session:
        _ = await session.window.page.goto(f"data:text/html,{quote(SCROLL_BOXES)}")
        lines, _ = await _observe(session)
        assert lines == [
            # scroll sizes are scaled like the box on screen
            "_[:]<button>Scaled</button>",
            # a reversed column scrolls up to older content (negative scroll offsets)
            "_[:]<button>Newest</button>",
            "_[:]<button>Older</button>",
            # a right-to-left box scrolls left from its right edge, not past it
            "_[:]<button>Far left</button>",
            "_[:]RTL_PAST_ITS_START",
            # an `auto` box clips the axis it has nothing to scroll on
            "_[:]SHIFTED_OUT_OF_ITS_PANEL",
            # `display: contents` has no box: its `overflow` clips nothing
            '_[:]<input placeholder="In a box without a box"></input>',
        ]


CHECKED = """
<h1>Top</h1>
<input type="checkbox" id="in-view" checked><label for="in-view">In view</label>
<div style="height: 2000px"></div>
<input type="checkbox" id="first"><label for="first">Checkbox 1</label>
<input type="checkbox" id="second" checked><label for="second">Checkbox 2</label>
<input type="radio" id="ticked" name="color"><label for="ticked">Ticked later</label>
<div role="switch" aria-checked="true" tabindex="0">Dark mode</div>
<input type="checkbox" id="locked" checked disabled><label for="locked">Locked</label>
<div style="height: 400px"></div>
"""


@pytest.mark.asyncio
async def test_checkboxes_outside_the_viewport_say_whether_they_are_checked() -> None:
    async with NotteSession(headless=True, viewport_width=1280, viewport_height=720) as session:
        _ = await session.window.page.goto(f"data:text/html,{quote(CHECKED)}")
        # the live state, not the attribute: checked by the user after the page loaded
        _ = await session.window.page.evaluate("document.getElementById('ticked').checked = true")
        lines, actions = await _observe(session)
        assert lines == [
            "_[:]Top",
            # in view, the checked state is the action's live state, not in the description
            'B1[:]<input type="checkbox"></input>',
            "_[:]In view",
            '_[:]<input type="checkbox"></input>',
            "_[:]Checkbox 1",
            '_[:]<input type="checkbox" checked></input>',
            "_[:]Checkbox 2",
            '_[:]<input type="radio" checked></input>',
            "_[:]Ticked later",
            '_[:]<div role="switch" checked>Dark mode</div>',
            '_[:]<input type="checkbox" disabled checked></input>',
            "_[:]Locked",
        ]
        assert [action_id for action_id, _ in actions] == ["B1"]


TOGGLES = """
<h1>Top</h1>
<button aria-pressed="true">Underline</button>
<div style="height: 2000px"></div>
<div role="toolbar"><button aria-pressed="true">Bold</button><button aria-pressed="false">Italic</button></div>
<div role="tablist"><button role="tab" aria-selected="true">Details</button><button role="tab">Reviews</button></div>
<button aria-expanded="true">Menu</button>
<button aria-expanded="false">Filters</button>
<button aria-pressed="true" disabled>Locked</button>
<div style="height: 400px"></div>
"""


@pytest.mark.asyncio
async def test_buttons_outside_the_viewport_say_whether_they_are_pressed_selected_or_expanded() -> None:
    async with NotteSession(headless=True, viewport_width=1280, viewport_height=720) as session:
        _ = await session.window.page.goto(f"data:text/html,{quote(TOGGLES)}")
        lines, actions = await _observe(session)
        assert lines == [
            "_[:]Top",
            # in view, the pressed state is the action's live state, not in the description
            "B1[:]<button>Underline</button>",
            "_[:]<button pressed>Bold</button>",
            "_[:]<button>Italic</button>",
            '_[:]<button role="tab" selected>Details</button>',
            '_[:]<button role="tab">Reviews</button>',
            "_[:]<button expanded>Menu</button>",
            "_[:]<button>Filters</button>",
            "_[:]<button disabled pressed>Locked</button>",
        ]
        assert [action_id for action_id, _ in actions] == ["B1"]


SCROLLED_IN_A_BOX = """
<h1>Contact</h1>
<div id="box" style="height: 100px; width: 300px; overflow-y: scroll">
  <input placeholder="Id" style="display: block; height: 30px">
  <div style="height: 150px"></div>
  <input placeholder="Subject">
  <a href="/terms">Terms</a>
</div>
<div style="height: 60px; overflow: hidden"><div style="height: 100px"></div><button>CLIPPED_AWAY</button></div>
"""


@pytest.mark.asyncio
async def test_controls_scrolled_out_of_a_box_in_view_are_described() -> None:
    # a scroll box in view hides the controls above and below its box: they are described like the controls
    # below the fold, which scrolling the box (not the page) brings into view
    async with NotteSession(headless=True, viewport_width=1280, viewport_height=720) as session:
        _ = await session.window.page.goto(f"data:text/html,{quote(SCROLLED_IN_A_BOX)}")
        lines, actions = await _observe(session)
        assert lines == [
            "_[:]Contact",
            'I1[:]<input placeholder="Id"></input>',
            '_[:]<input placeholder="Subject"></input>',
            "_[:]<a>Terms</a>",
            # a box that does not scroll clips for good: what it hides stays text
            "_[:]CLIPPED_AWAY",
        ]
        assert actions == [("I1", "Id")]

        _ = await session.window.page.evaluate("document.getElementById('box').scrollTop = 1000")
        lines, actions = await _observe(session)
        assert lines[:4] == [
            "_[:]Contact",
            '_[:]<input placeholder="Id"></input>',
            'I1[:]<input placeholder="Subject"></input>',
            'L1[:]<a href="/terms">Terms</a>',
        ]
        assert actions == [("I1", "Subject"), ("L1", "Terms")]


@pytest.mark.asyncio
async def test_controls_scrolled_out_of_a_shadow_host_are_described() -> None:
    async with NotteSession(headless=True, viewport_width=1280, viewport_height=720) as session:
        _ = await session.window.page.goto(
            'data:text/html,<div id="box" style="height:100px;width:300px;overflow-y:scroll"></div>'
        )
        _ = await session.window.page.evaluate(
            """document.getElementById('box').attachShadow({mode: 'open'}).innerHTML = `
              <input placeholder="Id" style="display:block;height:30px">
              <div style="height:150px"></div><input placeholder="Subject">
            `"""
        )
        lines, actions = await _observe(session)
        assert lines == [
            'I1[:]<input placeholder="Id"></input>',
            '_[:]<input placeholder="Subject"></input>',
        ]
        assert actions == [("I1", "Id")]

        _ = await session.window.page.evaluate("document.getElementById('box').scrollTop = 1000")
        lines, actions = await _observe(session)
        assert lines == [
            '_[:]<input placeholder="Id"></input>',
            'I1[:]<input placeholder="Subject"></input>',
        ]
        assert actions == [("I1", "Subject")]


@pytest.mark.asyncio
@pytest.mark.parametrize("scale", [1, 2])
async def test_slotted_controls_follow_their_shadow_scroll_box(scale: int) -> None:
    """Describe slotted controls outside their scroll box, then offer them after scrolling."""
    page = f"""
    <scroll-host style="display:block;transform:scale({scale});transform-origin:top left">
      <input placeholder="Id" style="display:block;height:30px;box-sizing:border-box">
      <div style="height:150px"></div>
      <button style="display:block;height:30px" onclick="document.title = 'Submitted'">Submit</button>
    </scroll-host>
    <script>
      document.querySelector('scroll-host').attachShadow({{mode:'open'}}).innerHTML =
        '<div id="box" style="height:100px;width:300px;overflow-y:scroll"><slot></slot></div>';
    </script>
    """
    async with NotteSession(headless=True, viewport_width=1280, viewport_height=720) as session:
        _ = await session.window.page.goto(f"data:text/html,{quote(page)}")
        lines, actions = await _observe(session)
        assert lines == ['I1[:]<input placeholder="Id"></input>', "_[:]<button>Submit</button>"]
        assert actions == [("I1", "Id")]
        result = await session.aexecute(type="fill", id="I1", value="Contact 42")
        assert result.success, result.message

        box = session.window.page.locator("scroll-host #box")
        _ = await box.evaluate("element => { element.scrollTop = 1000; }")
        lines, actions = await _observe(session)
        assert "B1[:]<button>Submit</button>" in lines
        assert actions == [("B1", "Submit")]
        result = await session.aexecute(type="click", id="B1")
        assert result.success, result.message
        assert await session.window.page.title() == "Submitted"

        _ = await box.evaluate("element => { element.scrollTop = 0; }")
        lines, actions = await _observe(session)
        assert "_[:]<button>Submit</button>" in lines
        assert actions == [("I1", "Id")]
        assert await session.window.page.locator("scroll-host input").input_value() == "Contact 42"


@pytest.mark.asyncio
@pytest.mark.parametrize("scale", [1, 2])
async def test_controls_behind_scroll_box_borders_are_described(scale: int) -> None:
    page = f"""
    <div id="box" style="height:100px;width:300px;border:20px solid;overflow-y:scroll;
                         transform:{"none" if scale == 1 else f"scale({scale})"};transform-origin:top left">
      <input placeholder="Top" style="display:block;height:20px;box-sizing:border-box">
      <div style="height:40px"></div>
      <input placeholder="Middle" style="display:block;height:20px;box-sizing:border-box">
      <div style="height:40px"></div>
      <input placeholder="Bottom" style="display:block;height:20px;box-sizing:border-box">
    </div>
    """
    async with NotteSession(headless=True, viewport_width=1280, viewport_height=720) as session:
        _ = await session.window.page.goto(f"data:text/html,{quote(page)}")
        # Both outside centers lie behind the borders, inside the box's outer bounding rect.
        _ = await session.window.page.evaluate("document.getElementById('box').scrollTop = 20")
        lines, actions = await _observe(session)
        assert lines == [
            '_[:]<input placeholder="Top"></input>',
            'I1[:]<input placeholder="Middle"></input>',
            '_[:]<input placeholder="Bottom"></input>',
        ]
        assert actions == [("I1", "Middle")]

        _ = await session.window.page.evaluate("document.getElementById('box').scrollTop = 0")
        _, actions = await _observe(session)
        assert actions == [("I1", "Top"), ("I2", "Middle")]

        _ = await session.window.page.evaluate("document.getElementById('box').scrollTop = 1000")
        _, actions = await _observe(session)
        assert actions == [("I1", "Middle"), ("I2", "Bottom")]


@pytest.mark.asyncio
@pytest.mark.parametrize("position", ["absolute", "fixed"])
async def test_positioned_boxless_wrappers_do_not_escape_scroll_clipping(position: str) -> None:
    page = f"""
    <div style="position:relative">
      <div id="box" style="height:100px;width:300px;overflow:auto">
        <div style="display:contents;position:{position}">
          <div style="height:150px"></div>
          <button onclick="this.dataset.clicked = 'true'">Later</button>
          <input placeholder="Later field">
        </div>
      </div>
    </div>
    """
    async with NotteSession(headless=True, viewport_width=1280, viewport_height=720) as session:
        _ = await session.window.page.goto(f"data:text/html,{quote(page)}")
        lines, actions = await _observe(session)
        assert lines == ["_[:]<button>Later</button>", '_[:]<input placeholder="Later field"></input>']
        assert actions == []

        _ = await session.window.page.evaluate("document.getElementById('box').scrollTop = 1000")
        _, actions = await _observe(session)
        assert actions == [("B1", "Later"), ("I1", "Later field")]
        await session.window.page.get_by_role("button", name="Later").click()
        assert await session.window.page.get_by_role("button", name="Later").get_attribute("data-clicked") == "true"


@pytest.mark.asyncio
@pytest.mark.parametrize("scale", [1, 2])
@pytest.mark.parametrize("direction", ["ltr", "rtl"])
async def test_controls_behind_horizontal_scroll_box_borders_are_described(scale: int, direction: str) -> None:
    page = f"""
    <div id="box" dir="{direction}" style="height:40px;width:100px;border:20px solid;overflow:auto;
                         transform:scale({scale});transform-origin:top left">
      <div style="display:flex;width:140px">
        <input placeholder="Start" style="width:20px;box-sizing:border-box;flex:none">
        <div style="width:40px;flex:none"></div>
        <input placeholder="Middle" style="width:20px;box-sizing:border-box;flex:none">
        <div style="width:40px;flex:none"></div>
        <input placeholder="End" style="width:20px;box-sizing:border-box;flex:none">
      </div>
    </div>
    """
    sign = 1 if direction == "ltr" else -1
    async with NotteSession(headless=True, viewport_width=1280, viewport_height=720) as session:
        _ = await session.window.page.goto(f"data:text/html,{quote(page)}")
        _ = await session.window.page.evaluate(
            "offset => { document.getElementById('box').scrollLeft = offset; }", sign * 20
        )
        lines, actions = await _observe(session)
        assert lines == [
            '_[:]<input placeholder="Start"></input>',
            'I1[:]<input placeholder="Middle"></input>',
            '_[:]<input placeholder="End"></input>',
        ]
        assert actions == [("I1", "Middle")]
        await session.window.page.get_by_placeholder("Middle").fill("Visible")
        assert await session.window.page.get_by_placeholder("Middle").input_value() == "Visible"

        _ = await session.window.page.evaluate("document.getElementById('box').scrollLeft = 0")
        _, actions = await _observe(session)
        assert actions == [("I1", "Start"), ("I2", "Middle")]

        _ = await session.window.page.evaluate(
            "offset => { document.getElementById('box').scrollLeft = offset; }", sign * 1000
        )
        _, actions = await _observe(session)
        assert actions == [("I1", "Middle"), ("I2", "End")]


@pytest.mark.asyncio
async def test_popup_descendants_escape_only_scrollers_outside_their_containing_block() -> None:
    boxes: list[str] = []
    for index, (position, transform) in enumerate(
        [("fixed", False), ("absolute", False), ("fixed", True), ("absolute", True)]
    ):
        left = index * 300
        popup_left = left if position == "fixed" and not transform else 0
        boxes.append(f"""
        <div style="position:absolute;top:20px;left:{left}px">
          <div class="box" style="height:100px;width:280px;overflow:auto;
                                  transform:{"translateZ(0)" if transform else "none"}">
            <div style="height:300px"></div><button>Clipped {index}</button>
            <div style="position:{position};top:150px;left:{popup_left}px">
              <div><button id="popup-{index}" onclick="this.dataset.clicked = 'true'">Popup {index}</button></div>
              <input placeholder="Popup field {index}">
            </div>
          </div>
        </div>
        """)

    async with NotteSession(headless=True, viewport_width=1280, viewport_height=720) as session:
        _ = await session.window.page.goto(f"data:text/html,{quote(''.join(boxes))}")
        # Browser hit testing confirms the untransformed popups escape, while transforms make the
        # scroller the containing block and clip both fixed and absolute popup descendants.
        for index in range(4):
            assert await session.window.page.locator(f"#popup-{index}").evaluate(
                """element => {
                    const rect = element.getBoundingClientRect();
                    return document.elementFromPoint(rect.x + rect.width / 2, rect.y + rect.height / 2) === element;
                }"""
            ) is (index < 2)

        lines, actions = await _observe(session)
        assert [label for _, label in actions] == ["Popup 0", "Popup field 0", "Popup 1", "Popup field 1"]
        for index in range(4):
            assert f"_[:]<button>Clipped {index}</button>" in lines
        for index in (2, 3):
            assert f"_[:]<button>Popup {index}</button>" in lines
            assert f'_[:]<input placeholder="Popup field {index}"></input>' in lines
        for index in (0, 1):
            await session.window.page.locator(f"#popup-{index}").click()
            assert await session.window.page.locator(f"#popup-{index}").get_attribute("data-clicked") == "true"

        # Escaping the scroller does not bypass the usual hit-target check for covered controls.
        _ = await session.window.page.evaluate("""() => {
            const cover = document.createElement('div');
            cover.id = 'cover';
            cover.style.cssText = 'position:fixed;top:150px;left:0;width:280px;height:60px;z-index:1000';
            document.body.append(cover);
        }""")
        _, actions = await _observe(session)
        assert [label for _, label in actions] == ["Popup 1", "Popup field 1"]

        _ = await session.window.page.evaluate(
            """() => {
                document.getElementById('cover').remove();
                document.querySelectorAll('.box').forEach(box => { box.scrollTop = 120; });
            }"""
        )
        _, actions = await _observe(session)
        assert [label for _, label in actions] == [
            label for index in range(4) for label in (f"Popup {index}", f"Popup field {index}")
        ]
        for index in (2, 3):
            await session.window.page.locator(f"#popup-{index}").click()
            assert await session.window.page.locator(f"#popup-{index}").get_attribute("data-clicked") == "true"
