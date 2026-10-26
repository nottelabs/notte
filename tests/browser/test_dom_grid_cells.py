"""`observe()` offers the focusable cells of an interactive grid, such as the days of a date picker.

A date picker dialog lays its days out in a `role="grid"` table, whose cells are focusable (`tabindex`, moved
with the arrow keys) and act on click, with no role, cursor or handler attribute that says so. Only the
buttons around the grid were offered: the dialog could be opened and its months turned, but no day picked.
The cells of a data table, and the empty cells before the first day of a month, are not controls.
"""

from urllib.parse import quote

import pytest
from notte_browser.session import NotteSession

PAGE = """
<input id="date" aria-label="Date">
<div role="dialog" aria-label="Choose a date">
  <button>Next month</button>
  <h2>November 2026</h2>
  <table role="grid">
    <tr><th>Su</th><th>Mo</th></tr>
    <tr><td tabindex="-1"></td><td tabindex="-1" data-date="2026-11-02">2</td></tr>
    <tr><td tabindex="0" data-date="2026-11-15" aria-selected="true">15</td><td tabindex="-1" data-date="2026-11-16">16</td></tr>
  </table>
  <div role="grid"><div role="row"><span role="gridcell" tabindex="-1" data-date="2026-11-30">30</span></div></div>
</div>
<table><tr><th>Name</th><th>Age</th></tr><tr><td tabindex="-1">Ada</td><td>36</td></tr></table>
<script>
  for (const cell of document.querySelectorAll("[data-date]")) {
    cell.addEventListener("click", () => { document.getElementById("date").value = cell.dataset.date; });
  }
</script>
"""


@pytest.mark.asyncio
async def test_the_days_of_a_date_grid_are_offered() -> None:
    async with NotteSession(headless=True) as session:
        _ = await session.window.page.goto(f"data:text/html,{quote(PAGE)}")
        observation = await session.aobserve()

        actions = [(action.id, action.text_label) for action in observation.space.interaction_actions]
        assert actions == [("I1", "Date"), ("B1", "Next month"), ("M1", "2"), ("M2", "15"), ("M3", "16"), ("M4", "30")]

        _ = await session.aexecute(type="click", id="M2")
        assert await session.window.page.input_value("#date") == "2026-11-15"


# the grid handles the clicks of its days on the table (a delegated handler): the table is offered, and its
# days too
DELEGATED_PAGE = """
<input id="date" aria-label="Date">
<table role="grid" onclick="const day = event.target.closest('[data-date]'); if (day) document.getElementById('date').value = day.dataset.date;">
  <tr><th>Su</th><th>Mo</th></tr>
  <tr><td tabindex="-1"></td><td tabindex="-1" data-date="2026-11-02">2</td></tr>
  <tr><td tabindex="0" data-date="2026-11-15">15</td><td tabindex="-1" data-date="2026-11-16">16</td></tr>
</table>
"""


@pytest.mark.asyncio
async def test_the_days_of_a_grid_with_a_delegated_handler_are_offered() -> None:
    async with NotteSession(headless=True) as session:
        _ = await session.window.page.goto(f"data:text/html,{quote(DELEGATED_PAGE)}")
        observation = await session.aobserve()

        days = {action.text_label: action.id for action in observation.space.interaction_actions}
        assert [label for label in days if label in ("2", "15", "16")] == ["2", "15", "16"]

        _ = await session.aexecute(type="click", id=days["15"])
        assert await session.window.page.input_value("#date") == "2026-11-15"
