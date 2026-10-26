"""`observe()` offers a control once, not again through the clickable containers around and inside it.

`cursor` is inherited: the label and counter wrappers of a link or a button have its pointer cursor, and
used to be offered as generic clickables (`M`), next to the link, which then had no text of its own.
ARIA widgets wrap native controls too: a `role="menuitem"` item around its link, a sortable column header
around its sort button. Each pair was offered twice.
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
<div class="clickable" onmousedown="this.dataset.pressed = 1"><button>Save</button></div>
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
        # a mouse handler other than onclick is a handler of its own too
        ("M4", "Save"),
        ("B4", "Save"),
    ]
    assert 'L1[:]<a href="/fork">Fork\n17.1k</a>' in observation.space.description


WRAPPED = """
<style>.sort { display: inline-block; width: 12px; height: 12px }</style>
<ul>
  <li role="menuitem"><a href="/" data-test="nav-home">Home</a></li>
  <li role="menuitem"><button data-test="nav-categories" aria-expanded="false">Categories</button></li>
</ul>
<table><thead><tr>
  <th style="cursor: pointer">Age <span class="sort" role="button" tabindex="0" aria-label="Age: Activate to sort"></span></th>
  <th style="cursor: pointer">Name <span class="sort" role="button" tabindex="0" aria-label="Sort"></span></th>
</tr></thead></table>
"""


@pytest.mark.asyncio
async def test_a_wrapper_that_says_nothing_more_than_its_control_is_not_offered() -> None:
    async with NotteSession(headless=True) as session:
        _ = await session.window.page.goto(f"data:text/html,{quote(WRAPPED)}")
        observation = await session.aobserve()

    actions = [(action.id, action.accessible_name) for action in observation.space.interaction_actions]
    assert actions == [
        ("L1", "Home"),
        ("B1", "Categories"),
        ("B2", "Age: Activate to sort"),
        # the header says "Name", which its button's name does not: both are kept
        ("M1", "Name Sort"),
        ("B3", "Sort"),
    ]
