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
<!-- A select the page hides behind its own button and list, kept in sync through its change event. -->
<select id="hidden" style="display: none"><option value="-1">-- select --</option><option value="2">CR Number</option><option value="7" label="VAT  Account">VAT</option><option value="8" disabled>Later</option></select>
<button id="hidden-toggle" type="button">-- select --</button>
<select id="hidden-group" style="display: none"><option value="a">A</option><optgroup label="Closed" disabled><option value="b">B</option></optgroup></select>
<select id="hidden-aria" style="display: none" aria-disabled="true"><option value="a">A</option><option value="b">B</option></select>
<select id="hidden-disabled" style="display: none" disabled><option value="x">X</option><option value="y">Y</option></select>
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
    const hidden = document.getElementById("hidden");
    hidden.addEventListener("change", () => {
        document.getElementById("hidden-toggle").textContent = hidden.selectedOptions[0].textContent;
    });
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


@pytest.mark.asyncio
@pytest.mark.parametrize("value", ["2", "CR Number"])
async def test_select_dropdown_option_selects_a_hidden_native_select(session: NotteSession, value: str) -> None:
    # Playwright waits for a select to be visible: one the page hides behind its own widget never is.
    res = await session.aexecute(
        SelectDropdownOptionAction(selector="#hidden", value=value, timeout=3000), raise_on_failure=True
    )

    assert res.success
    page = session.window.page
    assert await page.locator("#hidden").input_value() == "2"
    # the change event reached the page's widget
    assert await page.locator("#hidden-toggle").text_content() == "CR Number"


@pytest.mark.asyncio
async def test_select_dropdown_option_leaves_a_hidden_disabled_select_alone(session: NotteSession) -> None:
    res = await session.aexecute(
        SelectDropdownOptionAction(selector="#hidden-disabled", value="y", timeout=1000), raise_on_failure=False
    )

    assert not res.success
    assert await session.window.page.locator("#hidden-disabled").input_value() == "x"


@pytest.mark.asyncio
async def test_select_dropdown_option_waits_for_a_hidden_select_to_be_enabled(session: NotteSession) -> None:
    # A dependent select: disabled and empty until the page fills it in.
    page = session.window.page
    _ = await page.evaluate("""() => setTimeout(() => {
        const select = document.getElementById("hidden-disabled");
        select.add(new Option("Z", "z"));
        select.disabled = false;
    }, 500)""")
    res = await session.aexecute(
        SelectDropdownOptionAction(selector="#hidden-disabled", value="z", timeout=3000), raise_on_failure=True
    )

    assert res.success
    assert await page.locator("#hidden-disabled").input_value() == "z"


@pytest.mark.asyncio
async def test_select_dropdown_option_does_not_set_a_hidden_select_disabled_before_its_option_arrives(
    session: NotteSession,
) -> None:
    page = session.window.page
    _ = await page.evaluate("""() => setTimeout(() => {
        const select = document.getElementById("hidden");
        select.disabled = true;
        select.add(new Option("Late", "late"));
    }, 300)""")
    res = await session.aexecute(
        SelectDropdownOptionAction(selector="#hidden", value="late", timeout=1500), raise_on_failure=False
    )

    assert not res.success
    assert await page.locator("#hidden").input_value() == "-1"


@pytest.mark.asyncio
async def test_select_dropdown_option_matches_a_hidden_option_label_with_collapsed_whitespace(
    session: NotteSession,
) -> None:
    res = await session.aexecute(
        SelectDropdownOptionAction(selector="#hidden", value="VAT Account", timeout=3000), raise_on_failure=True
    )

    assert res.success
    assert await session.window.page.locator("#hidden").input_value() == "7"


@pytest.mark.asyncio
async def test_select_dropdown_option_does_not_set_a_hidden_select_disabled_before_its_option_is_enabled(
    session: NotteSession,
) -> None:
    page = session.window.page
    _ = await page.evaluate("""() => {
        const select = document.getElementById("hidden");
        setTimeout(() => { select.disabled = true; }, 300);
        setTimeout(() => { select.options[3].disabled = false; }, 600);
    }""")
    res = await session.aexecute(
        SelectDropdownOptionAction(selector="#hidden", value="8", timeout=1500), raise_on_failure=False
    )

    assert not res.success
    assert await page.locator("#hidden").input_value() == "-1"


@pytest.mark.asyncio
@pytest.mark.parametrize("selector", ["#hidden-group", "#hidden-aria"])
async def test_select_dropdown_option_does_not_pick_a_disabled_hidden_option(
    session: NotteSession, selector: str
) -> None:
    # an option in a disabled optgroup, a select disabled for assistive technology
    res = await session.aexecute(
        SelectDropdownOptionAction(selector=selector, value="b", timeout=1000), raise_on_failure=False
    )

    assert not res.success
    assert await session.window.page.locator(selector).input_value() == "a"
