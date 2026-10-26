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
