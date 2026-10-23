"""`observe()` offers a control once, not again through the clickable containers around and inside it.

`cursor` is inherited: the label and counter wrappers of a link or a button have its pointer cursor, and
used to be offered as generic clickables (`M`), next to the link, which then had no text of its own.
"""

from urllib.parse import quote

import pytest
from notte_browser.session import NotteSession

PAGE = """
<style>.clickable { cursor: pointer }</style>
<a href="/fork" class="clickable"><span><span>Fork</span> <span><b>17.1k</b></span></span></a>
<div class="clickable" id="search">Go <input type="submit" value="Go"></div>
<div class="clickable" onclick="this.dataset.clicked = 1"><span>Widgets</span></div>
<div class="clickable" onclick="this.dataset.clicked = 1">10:40 AM Paris - Tokyo
  <button aria-label="Emissions"><b>i</b></button>
</div>
<button>Tag <span onclick="this.dataset.removed = 1">x</span></button>
"""


@pytest.mark.asyncio
async def test_a_control_is_offered_once() -> None:
    async with NotteSession(headless=True) as session:
        _ = await session.window.page.goto(f"data:text/html,{quote(PAGE)}")
        observation = await session.aobserve()

    actions = [(action.id, action.text_label) for action in observation.space.interaction_actions]
    assert actions == [
        ("L1", "Fork 17.1k"),
        ("B1", "Go"),
        ("M1", "Widgets"),
        ("M2", "10:40 AM Paris - Tokyo i"),
        ("B2", "i"),
        # a nested element with a click handler of its own may do something else
        ("B3", "Tag x"),
        ("M3", "x"),
    ]
    assert 'L1[:]<a href="/fork">Fork\n17.1k</a>' in observation.space.description
