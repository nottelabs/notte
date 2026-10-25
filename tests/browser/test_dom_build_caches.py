"""`buildDomNode.js` reads some things once per build: the `:hover` rules that set a cursor, the positions of
siblings (for the XPaths), the ancestors that clip an element's overflow, the rects of text nodes.

Each `observe()` builds again, so a page that changed between two observations is described as it is now,
never with what an earlier build read.
"""

from urllib.parse import quote

import pytest
from notte_browser.session import NotteSession

HOVER = """
<style>
  .other:hover { color: red; }
  .card:hover { color: blue; }
  .unmatched:hover { cursor: pointer; }
  .first:hover { cursor: default; }
  .first:hover { cursor: pointer; }
  .card:hover { cursor: pointer; }
</style>
<div class="card">Open card</div>
<div class="first">First rule wins</div>
<div class="later">Later card</div>
"""


async def _labels(session: NotteSession) -> list[str]:
    obs = await session.aobserve()
    return [action.text_label for action in obs.space.interaction_actions]


async def _xpaths(session: NotteSession) -> dict[str, str]:
    obs = await session.aobserve()
    xpaths: dict[str, str] = {}
    for action in obs.space.interaction_actions:
        node = session.snapshot.dom_node.find(action.id)
        assert node is not None and node.computed_attributes.selectors is not None
        xpaths[action.text_label] = node.computed_attributes.selectors.xpath_selector
    return xpaths


@pytest.mark.asyncio
async def test_hover_cursor_rules_are_read_on_each_observation() -> None:
    async with NotteSession(headless=True, viewport_width=1280, viewport_height=720) as session:
        _ = await session.window.page.goto(f"data:text/html,{quote(HOVER)}")
        # the first matching `:hover` rule that sets a cursor decides: `default` is not a pointer
        assert await _labels(session) == ["Open card"]

        # a rule removed and one added between two observations
        _ = await session.window.page.evaluate("""() => {
            const sheet = document.styleSheets[0];
            sheet.deleteRule(sheet.cssRules.length - 1);
            sheet.insertRule(".later:hover { cursor: pointer; }", sheet.cssRules.length);
        }""")
        assert await _labels(session) == ["Later card"]


SIBLINGS = """
<div id="list"><button>Alpha</button><button>Beta</button></div>
<div><a href="/only">Only link</a></div>
"""


@pytest.mark.asyncio
async def test_xpaths_follow_the_siblings_of_each_observation() -> None:
    async with NotteSession(headless=True, viewport_width=1280, viewport_height=720) as session:
        _ = await session.window.page.goto(f"data:text/html,{quote(SIBLINGS)}")
        assert await _xpaths(session) == {
            "Alpha": "html/body/div[1]/button[1]",
            "Beta": "html/body/div[1]/button[2]",
            # the only element of its tag among its siblings has no index
            "Only link": "html/body/div[2]/a",
        }

        _ = await session.window.page.evaluate("""() => {
            const button = document.createElement("button");
            button.textContent = "Zero";
            document.getElementById("list").prepend(button);
            document.body.prepend(document.createElement("div"));
        }""")
        assert await _xpaths(session) == {
            "Zero": "html/body/div[2]/button[1]",
            "Alpha": "html/body/div[2]/button[2]",
            "Beta": "html/body/div[2]/button[3]",
            "Only link": "html/body/div[3]/a",
        }


REACH = """
<h1>Top</h1>
<div style="height: 2000px"></div>
<div id="box" style="height: 40px; overflow: auto">
  <div style="height: 100px"></div><button>Inside the box</button>
</div>
<p>Below the fold</p>
<div style="height: 400px"></div>
"""


@pytest.mark.asyncio
async def test_reach_and_text_are_read_on_each_observation() -> None:
    async with NotteSession(headless=True, viewport_width=1280, viewport_height=720) as session:
        _ = await session.window.page.goto(f"data:text/html,{quote(REACH)}")
        obs = await session.aobserve()
        lines = obs.space.description.splitlines()[1:]
        # the box scrolls to the button: it is described off-screen
        assert lines == ["_[:]Top", "_[:]<button>Inside the box</button>", "_[:]Below the fold"]

        # the box no longer scrolls: scrolling cannot reveal the button, which stays text
        _ = await session.window.page.evaluate("document.getElementById('box').style.overflow = 'hidden'")
        obs = await session.aobserve()
        assert obs.space.description.splitlines()[1:] == ["_[:]Top", "_[:]Inside the box", "_[:]Below the fold"]

        # scrolled into view, the text is in the viewport
        texts = [node for node in session.snapshot.dom_node.flatten() if node.text == "Below the fold"]
        assert [node.computed_attributes.in_viewport for node in texts] == [False]
        _ = await session.window.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        _ = await session.aobserve()
        texts = [node for node in session.snapshot.dom_node.flatten() if node.text == "Below the fold"]
        assert [node.computed_attributes.in_viewport for node in texts] == [True]
