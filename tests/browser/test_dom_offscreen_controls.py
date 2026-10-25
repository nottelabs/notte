"""`observe()` describes the controls above and below the viewport without offering them as actions.

Only the elements in the viewport get an id, while the description covers the whole page. A link below the
fold used to be rendered as its text alone, and a field below the fold not at all, so a caller reading the
description could not tell that the page links somewhere or has a field further down. They are now rendered
like the controls in view, without an id and with fewer attributes, and their nodes are marked
`DomNode.offscreen`. Hidden controls stay out, as their text does.
"""

from urllib.parse import quote

import pytest
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
