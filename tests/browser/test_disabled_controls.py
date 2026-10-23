"""`observe()` describes disabled controls without offering them as actions.

A disabled control used to be left out of the description (an input) or reduced to its text (a button), so a
caller could not tell that the control it needs exists but is not ready yet. It is now rendered without an id,
with a `disabled` attribute, and its node is marked `DomNode.disabled`. Controls of a disabled `<fieldset>`
were offered as actions (their `.disabled` property is false): they are now disabled controls too.
"""

from urllib.parse import quote

import pytest
from notte_browser.session import NotteSession
from notte_core.element_state import ElementState

PAGE = """
<label for="name">Name</label><input id="name" disabled>
<button id="enable" onclick="document.getElementById('name').disabled = false">Enable</button>
<button disabled>Submit</button>
<button style="cursor: not-allowed" disabled>Styled</button>
<fieldset disabled><legend>Shipping</legend><input name="city" placeholder="City"></fieldset>
<div role="button" aria-disabled="true" tabindex="0">Next step</div>
<a href="/next">Next page <button disabled>Save</button></a>
"""


async def _observe(session: NotteSession) -> tuple[list[str], list[tuple[str, str]]]:
    obs = await session.aobserve()
    lines = obs.space.description.splitlines()[1:]
    return lines, [(action.id, action.text_label) for action in obs.space.interaction_actions]


@pytest.mark.asyncio
async def test_disabled_controls_are_described_without_actions() -> None:
    async with NotteSession(headless=True) as session:
        _ = await session.window.page.goto(f"data:text/html,{quote(PAGE)}")
        lines, actions = await _observe(session)

        assert lines == [
            "_[:]Name",
            "_[:]<input disabled></input>",
            "B1[:]<button>Enable</button>",
            "_[:]<button disabled>Submit</button>",
            "_[:]<button disabled>Styled</button>",
            "_[:]Shipping",
            '_[:]<input placeholder="City" name="city" disabled></input>',
            '_[:]<div tabindex="0" role="button" disabled>Next step</div>',
            # inside a link, a disabled button is described on its own, like an enabled one
            'L1[:]<a href="/next">Next page</a>',
            "_[:]<button disabled>Save</button>",
        ]
        assert actions == [("B1", "Enable"), ("L1", "Next page Save")]

        disabled = [node for node in session.snapshot.dom_node.flatten() if node.disabled]
        assert [(node.id, node.accessible_name) for node in disabled] == [
            (None, "Name"),
            (None, "Submit"),
            (None, "Styled"),
            (None, "City"),
            (None, "Next step"),
            (None, "Save"),
        ]
        assert disabled[0].state == ElementState(value="")

        # once enabled, the field is an action like any other, and the other ids do not move
        _ = await session.aexecute(type="click", id="B1")
        lines, actions = await _observe(session)
        assert lines[1] == "I1[:]<input></input>"
        assert actions == [("I1", ""), ("B1", "Enable"), ("L1", "Next page Save")]
