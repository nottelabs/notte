"""`observe()` offers the column headers that sort a table on a click handler of their own.

Table plugins (jQuery's tablesorter) add a click listener to each header cell, with no role, tabindex or pointer
cursor: the page script that builds the observation cannot see listeners, so no header was offered and the table
could not be sorted. The DevTools protocol lists them: column headers with a click listener of their own are
offered as clickables. Headers without one, and listeners on the table around them, offer nothing.
"""

from urllib.parse import quote

import pytest
from notte_browser.dom import parsing
from notte_browser.driver import ElementHandle, Page, evaluate_in_main_world
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


@pytest.mark.asyncio
async def test_a_cloned_bridge_marker_cannot_transfer_a_click_listener() -> None:
    """A page observer cloning marked headers cannot create false actions or leave markers behind."""
    observer = """
    <script>
      new MutationObserver(records => {
        for (const record of records) {
          const header = record.target;
          if (record.attributeName.startsWith('data-notte-header-') &&
              header.hasAttribute(record.attributeName) && header.isConnected) {
            header.replaceWith(header.cloneNode(true));
          }
        }
      }).observe(document.documentElement, {subtree: true, attributes: true});
    </script>
    """
    async with NotteSession(headless=True) as session:
        page = session.window.page
        _ = await page.goto(f"data:text/html,{quote(PAGE + observer)}")
        observation = await session.aobserve()
        actions = [(action.id, action.text_label) for action in observation.space.interaction_actions]
        assert actions == [("M1", "Name"), ("M2", "Due")]
        _ = await session.aexecute(type="click", id="M2")
        assert await page.inner_text("#dues tbody tr:first-child td:nth-child(2)") == "$51.00"
        assert await page.evaluate(
            """() => [...document.querySelectorAll('th')].every(header =>
                header.getAttributeNames().every(name => !name.startsWith('data-notte-header-')))"""
        )
        assert await evaluate_in_main_world(
            page.main_frame,
            "!Object.getOwnPropertyNames(globalThis).some(name => name.startsWith('__notte_headers_'))",
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", ["insert", "reorder", "replace", "navigate"])
async def test_listener_hints_keep_header_identity(monkeypatch: pytest.MonkeyPatch, mutation: str) -> None:
    probe = parsing.headers_with_click_listeners

    async def probe_then_change_table(page: Page) -> list[ElementHandle]:
        headers = await probe(page)
        assert len(headers) == 2
        # The CDP bridge must not leave its temporary attributes on the page.
        assert await page.evaluate(
            """() => [...document.querySelectorAll('th')].every(header =>
                header.getAttributeNames().every(name => !name.startsWith('data-notte-header-')))"""
        )
        if mutation == "navigate":
            _ = await page.goto(f"data:text/html,{quote('<table><tr><th>Replacement</th></tr></table>')}")
        else:
            _ = await page.evaluate(
                """mutation => {
                    const row = document.querySelector('#dues thead tr');
                    if (mutation === 'insert') row.insertAdjacentHTML('afterbegin', '<th>Inserted</th>');
                    if (mutation === 'reorder') row.prepend(row.lastElementChild);
                    if (mutation === 'replace') row.innerHTML = '<th>Replacement</th>';
                }""",
                mutation,
            )
        return headers

    monkeypatch.setattr(parsing, "headers_with_click_listeners", probe_then_change_table)
    async with NotteSession(headless=True) as session:
        _ = await session.window.page.goto(f"data:text/html,{quote(PAGE)}")
        observation = await session.aobserve()
        labels = [action.text_label for action in observation.space.interaction_actions]
        assert labels == (["Name", "Due"] if mutation in {"insert", "reorder"} else [])
