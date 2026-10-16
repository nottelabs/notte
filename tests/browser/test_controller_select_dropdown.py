from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from notte_browser.session import NotteSession
from notte_core.actions import SelectDropdownOptionAction
from notte_core.errors import ActionExecutionError

# A custom dropdown: the listbox opens on click and its options are plain divs.
PAGE = """
<div id="fruit" role="combobox" aria-controls="fruit-list" aria-expanded="false" tabindex="0">Pick a fruit</div>
<div id="fruit-list" role="listbox" hidden>
    <div role="option" data-value="a">Apple</div>
    <div role="option" data-value="b">Banana</div>
</div>
<ul id="nav"><li>Banana</li><li id="kiwi" onclick="this.dataset.clicked = 'yes'">Kiwi</li></ul>
<select id="native"><option value="x">X</option><option value="y">Y</option></select>
<script>
    const box = document.getElementById("fruit");
    const list = document.getElementById("fruit-list");
    box.addEventListener("click", () => { list.hidden = false; box.setAttribute("aria-expanded", "true"); });
    for (const option of list.querySelectorAll("[role=option]")) {
        option.addEventListener("click", () => {
            box.textContent = option.textContent;
            box.dataset.selected = option.dataset.value;
            list.hidden = true;
        });
    }
</script>
"""


@pytest_asyncio.fixture(loop_scope="function")
async def session() -> AsyncIterator[NotteSession]:
    async with NotteSession(headless=True) as session:
        await session.window.page.set_content(PAGE)
        yield session


@pytest.mark.asyncio
@pytest.mark.parametrize("value", ["Banana", "b"])
async def test_select_dropdown_option_picks_the_option_of_a_custom_dropdown(session: NotteSession, value: str) -> None:
    res = await session.aexecute(SelectDropdownOptionAction(selector="#fruit", value=value), raise_on_failure=True)

    assert res.success
    assert await session.window.page.locator("#fruit").get_attribute("data-selected") == "b"
    assert await session.window.page.locator("#fruit").text_content() == "Banana"


@pytest.mark.asyncio
async def test_select_dropdown_option_fails_when_no_option_matches(session: NotteSession) -> None:
    res = await session.aexecute(SelectDropdownOptionAction(selector="#fruit", value="Cherry"), raise_on_failure=False)

    assert not res.success
    assert isinstance(res.exception, ActionExecutionError)
    assert "Cherry" in str(res.exception)
    assert await session.window.page.locator("#fruit").get_attribute("data-selected") is None


@pytest.mark.asyncio
async def test_select_dropdown_option_does_not_click_items_outside_the_named_list(session: NotteSession) -> None:
    # "Kiwi" is only a navigation item: the combobox names its listbox, so nothing else is a candidate.
    res = await session.aexecute(SelectDropdownOptionAction(selector="#fruit", value="Kiwi"), raise_on_failure=False)

    assert not res.success
    assert isinstance(res.exception, ActionExecutionError)
    assert await session.window.page.locator("#kiwi").get_attribute("data-clicked") is None
    assert await session.window.page.locator("#fruit").get_attribute("data-selected") is None


@pytest.mark.asyncio
async def test_select_dropdown_option_still_selects_native_select(session: NotteSession) -> None:
    res = await session.aexecute(SelectDropdownOptionAction(selector="#native", value="y"), raise_on_failure=True)

    assert res.success
    assert await session.window.page.locator("#native").input_value() == "y"
