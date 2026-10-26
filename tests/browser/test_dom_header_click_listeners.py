"""`observe()` offers the column headers that sort a table on a click handler of their own.

Table plugins (jQuery's tablesorter) add a click listener to each header cell, with no role, tabindex or pointer
cursor: the page script that builds the observation cannot see listeners, so no header was offered and the table
could not be sorted. The DevTools protocol lists them: column headers with a click listener of their own are
offered as clickables. Headers without one, and listeners on the table around them, offer nothing.
"""

from urllib.parse import quote

import pytest
from notte_browser.session import NotteSession

PAGE = """
<table id="dues">
  <thead><tr><th>Name</th><th>Due</th><th>Note</th></tr></thead>
  <tbody><tr><td>Ada</td><td>$50.00</td><td></td></tr><tr><td>Alan</td><td>$51.00</td><td></td></tr></tbody>
</table>
<table id="other"><thead><tr><th>Delegated</th></tr></thead></table>
<script>
  const table = document.getElementById("dues");
  for (const th of [...table.querySelectorAll("th")].slice(0, 2)) {
    th.addEventListener("click", () => {
      const column = th.cellIndex;
      const rows = [...table.tBodies[0].rows].sort((a, b) =>
        b.cells[column].textContent.localeCompare(a.cells[column].textContent));
      table.tBodies[0].append(...rows);
    });
  }
  document.getElementById("other").addEventListener("click", () => {});
</script>
"""


@pytest.mark.asyncio
async def test_headers_with_a_click_listener_are_offered() -> None:
    async with NotteSession(headless=True) as session:
        _ = await session.window.page.goto(f"data:text/html,{quote(PAGE)}")
        observation = await session.aobserve()

        actions = [(action.id, action.text_label) for action in observation.space.interaction_actions]
        assert actions == [("M1", "Name"), ("M2", "Due")]

        _ = await session.aexecute(type="click", id="M2")
        first_due = await session.window.page.inner_text("#dues tbody tr:first-child td:nth-child(2)")
        assert first_due == "$51.00"
