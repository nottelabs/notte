"""An action on an element whose part of the page re-rendered after it was observed.

The CSS and XPath selectors of an observed element are paths from the root of the page. When a list of
results updates (Google Flights adds a block above its results while they load), the paths of its rows
change and match nothing. The element is then found again by its role, name and text, if exactly one
element matches.
"""

from urllib.parse import quote

import pytest
from notte_browser.session import NotteSession

ROWS = ["Paris 10:40 AM", "Tokyo 6:40 PM"]
PAGE = """
<style>.row { cursor: pointer }</style>
<div id="results"><ul>{rows}</ul></div>
<script>
  document.addEventListener("click", (event) => {
    const row = event.target.closest(".row");
    if (row) document.body.dataset.clicked = row.textContent;
  });
</script>
"""


def _rows(texts: list[str]) -> str:
    return "".join(f'<li><div class="row">{text}</div></li>' for text in texts)


async def _observe_then_rerender(session: NotteSession, rows: list[str], observed: list[str] = ROWS) -> str:
    _ = await session.window.page.goto(f"data:text/html,{quote(PAGE.replace('{rows}', _rows(observed)))}")
    observation = await session.aobserve()
    tokyo = [action for action in observation.space.interaction_actions if action.text_label == "Tokyo 6:40 PM"][-1]
    # the list is rebuilt one level deeper, below a new block: the observed paths match nothing
    _ = await session.window.page.evaluate(
        "html => { document.getElementById('results').innerHTML = html }",
        f"<p>Prices updated</p><section><ul>{_rows(rows)}</ul></section>",
    )
    return tokyo.id


@pytest.mark.asyncio
async def test_a_moved_element_is_found_again() -> None:
    async with NotteSession(headless=True) as session:
        tokyo = await _observe_then_rerender(session, ["Lisbon 7:05 AM", *ROWS])
        result = await session.aexecute(type="click", id=tokyo, raise_on_failure=False)
        clicked = await session.window.page.evaluate("() => document.body.dataset.clicked")

    assert result.success, result.message
    assert clicked == "Tokyo 6:40 PM"


@pytest.mark.parametrize(
    ("observed", "rows"),
    [
        (ROWS, ["Paris 10:40 AM"]),
        (ROWS, ["Tokyo 6:40 PM", "Tokyo 6:40 PM"]),
        # the observed row was one of two identical rows: the remaining one may be the other
        (["Tokyo 6:40 PM", *ROWS], ["Tokyo 6:40 PM"]),
    ],
    ids=["element removed", "element ambiguous", "element ambiguous when observed"],
)
@pytest.mark.asyncio
async def test_an_element_that_cannot_be_found_again_is_not_guessed(observed: list[str], rows: list[str]) -> None:
    async with NotteSession(headless=True) as session:
        tokyo = await _observe_then_rerender(session, rows, observed)
        result = await session.aexecute(type="click", id=tokyo, raise_on_failure=False)
        clicked = await session.window.page.evaluate("() => document.body.dataset.clicked")

    assert not result.success
    assert "could not be located" in result.message
    assert clicked is None
