"""A fill checks that a text field kept the text, types it key by key when it did not, and fails when the field does
not keep it either way.

Playwright's `fill` inserts the whole text in one input event, without key events. A masked input that refuses
characters on keydown and reverts any other value (a controlled input, as on a shop's checkout phone field) throws
such a value away: the field stayed empty and the fill reported success.
"""

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from notte_browser import execution
from notte_browser.session import NotteSession
from notte_core.actions import FillAction, SelectDropdownOptionAction

# Counts the keys pressed in the page (in the DOM: page.evaluate may run in an isolated world).
KEY_COUNTER = """<script>
document.addEventListener("keydown", () => {
    document.body.dataset.keys = String(Number(document.body.dataset.keys || 0) + 1);
}, true);
</script>"""

# Refuses keys other than digits and "+", and reverts a value with another character, at once or `later`.
REFUSING = """<input id="phone" aria-label="Mobile number (XXX XXX XXXX)">
<script>
const phone = document.getElementById("phone");
let kept = "";
phone.addEventListener("keydown", (event) => {
    if (event.key.length === 1 && !/[0-9+]/.test(event.key)) event.preventDefault();
});
phone.addEventListener("input", () => {
    const revert = () => { if (/^[0-9+]*$/.test(phone.value)) kept = phone.value; else phone.value = kept; };
    if (LATER) setTimeout(revert, 0); else revert();
});
</script>"""

# Formats the digits as "(415) 555-0123".
FORMATTING = """<input id="phone" aria-label="Phone">
<script>
const phone = document.getElementById("phone");
phone.addEventListener("input", () => {
    const d = phone.value.replace(/\\D/g, "").slice(0, 10);
    phone.value = d.length > 6 ? `(${d.slice(0, 3)}) ${d.slice(3, 6)}-${d.slice(6)}` : d;
});
</script>"""

# Keeps a fixed "+1 " country code before the digits.
PREFIXED = """<input id="phone" aria-label="Phone" value="+1 ">
<script>
const phone = document.getElementById("phone");
phone.addEventListener("input", () => {
    phone.value = "+1 " + phone.value.replace(/^\\+1 ?/, "").replace(/\\D/g, "");
});
</script>"""

# Takes nothing: every key is refused and every value reverted.
REFUSING_ALL = """<input id="phone" aria-label="Phone">
<script>
const phone = document.getElementById("phone");
phone.addEventListener("keydown", (event) => { if (event.key.length === 1) event.preventDefault(); });
phone.addEventListener("input", () => { phone.value = ""; });
</script>"""

PLAIN = """<input id="input" value="old">
<input id="tel" type="tel">
<textarea id="textarea">old</textarea>
<div id="editable" contenteditable="true">old</div>
<input id="date" type="date">
<input id="number" type="number">
<select id="select"><option value="">Choose</option><option value="fr">France</option></select>
<input id="short" maxlength="4">"""


@pytest_asyncio.fixture(loop_scope="function")
async def session() -> AsyncIterator[NotteSession]:
    async with NotteSession(headless=True) as session:
        yield session


async def _open(session: NotteSession, page: str) -> None:
    await session.window.page.set_content(f"<html><body>{page}{KEY_COUNTER}</body></html>")


async def _keys(session: NotteSession) -> int:
    return int(await session.window.page.locator("body").get_attribute("data-keys") or 0)


async def _value(session: NotteSession, selector: str) -> str:
    return await session.window.page.locator(selector).input_value()


@pytest.mark.asyncio
@pytest.mark.parametrize("later", [False, True], ids=["reverted at once", "reverted after the input event"])
@pytest.mark.parametrize(
    ("text", "expected"),
    [("415 555 0123", "4155550123"), ("+1 415 555 0123", "+14155550123"), ("(415) 555-0123", "4155550123")],
)
async def test_a_field_that_refuses_the_filled_text_is_typed_into(
    session: NotteSession, later: bool, text: str, expected: str
) -> None:
    await _open(session, REFUSING.replace("LATER", "true" if later else "false"))
    result = await session.aexecute(FillAction(selector="#phone", value=text), raise_on_failure=False)
    assert result.success, result.message
    assert await _value(session, "#phone") == expected


@pytest.mark.asyncio
async def test_a_refused_fill_replaces_the_previous_value(session: NotteSession) -> None:
    await _open(session, REFUSING.replace("LATER", "false"))
    _ = await session.aexecute(FillAction(selector="#phone", value="5550000"), raise_on_failure=True)
    _ = await session.aexecute(FillAction(selector="#phone", value="415 555 0123"), raise_on_failure=True)
    assert await _value(session, "#phone") == "4155550123"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("page", "text", "expected"),
    [
        (FORMATTING, "4155550123", "(415) 555-0123"),
        (FORMATTING, "415.555.0123", "(415) 555-0123"),
        (PREFIXED, "4155550123", "+1 4155550123"),
        (PREFIXED, "+1 415 555 0123", "+1 4155550123"),
    ],
    ids=["formatted", "formatted from dots", "fixed country code", "typed country code"],
)
async def test_a_mask_that_formats_the_text_keeps_it(
    session: NotteSession, page: str, text: str, expected: str
) -> None:
    await _open(session, page)
    result = await session.aexecute(FillAction(selector="#phone", value=text), raise_on_failure=True)
    assert result.success
    assert await _value(session, "#phone") == expected
    # filled at once: not typed again
    assert await _keys(session) == 0


@pytest.mark.asyncio
async def test_a_field_its_selector_no_longer_finds_is_read_back(session: NotteSession) -> None:
    # An address autocomplete changed the page as the field was typed into, so that its selector found nothing: the
    # read back waited for the field until the action's timeout.
    await _open(session, '<input id="address" oninput="this.id = \'address-typed\'">')
    result = await session.aexecute(
        FillAction(selector="#address", value="777 Florida St", timeout=3000), raise_on_failure=False
    )
    assert result.success, result.message
    assert await _value(session, "#address-typed") == "777 Florida St"


@pytest.mark.asyncio
async def test_a_fill_that_navigates_is_done(session: NotteSession) -> None:
    # A one-time code form goes on at its last digit: the field is gone before it is read back.
    page = session.window.page
    pages = {
        "http://otp.test/": '<input id="code" oninput="if (this.value.length === 6) location.href = \'/done\'">',
        "http://otp.test/done": "<p>Verified</p>",
    }
    _ = await page.route(
        "http://otp.test/**", lambda route: route.fulfill(body=pages[route.request.url], content_type="text/html")
    )
    _ = await page.goto("http://otp.test/")
    result = await session.aexecute(FillAction(selector="#code", value="123456"), raise_on_failure=False)
    assert result.success, result.message
    await page.wait_for_url("http://otp.test/done")


@pytest.mark.asyncio
async def test_a_field_the_page_replaced_is_read_where_its_selector_finds_it(session: NotteSession) -> None:
    # The page swaps the field for an empty one as it is typed into: the element act filled, now off the page, still
    # holds the text.
    await _open(
        session,
        """<input id="phone" oninput="if (!window.swapped) { window.swapped = true;
          const empty = document.createElement('input'); empty.id = 'phone'; this.replaceWith(empty); }">""",
    )
    result = await session.aexecute(FillAction(selector="#phone", value="4155550123"), raise_on_failure=False)
    assert result.success, result.message
    assert await _value(session, "#phone") == "4155550123"


@pytest.mark.asyncio
async def test_another_field_the_selector_finds_after_a_removal_is_left_alone(session: NotteSession) -> None:
    # the filled field goes away: its selector now finds the next input, which is another field
    await _open(session, '<input id="code" oninput="this.remove()"><input id="other" value="keep">')
    result = await session.aexecute(
        FillAction(selector="input:nth-of-type(1)", value="4155550123", timeout=3000), raise_on_failure=False
    )
    assert result.success, result.message
    assert await _value(session, "#other") == "keep"


@pytest.mark.asyncio
async def test_an_unnamed_field_that_went_away_is_not_followed(session: NotteSession) -> None:
    # two inputs with nothing that names them look the same: the next one is another field, never typed into
    await _open(
        session,
        """<input oninput="if (this.value) this.remove()"><input value="keep">""",
    )
    result = await session.aexecute(
        FillAction(selector="input:nth-of-type(1)", value="4155550123", timeout=3000), raise_on_failure=False
    )
    assert result.success, result.message
    assert await _value(session, "input") == "keep"
    assert await _keys(session) == 0


@pytest.mark.asyncio
async def test_a_paste_into_a_field_its_handler_renames_is_read_back(session: NotteSession) -> None:
    # a leading space makes the fill a paste; the page renames the field as it is typed into
    await _open(session, """<input id="code" oninput="this.id = 'code-typed'">""")
    result = await session.aexecute(FillAction(selector="#code", value=" AB12", timeout=3000), raise_on_failure=False)
    assert result.success, result.message
    assert (await _value(session, "#code-typed")).strip() == "AB12"


@pytest.mark.asyncio
async def test_a_refused_paste_is_typed_into(session: NotteSession) -> None:
    # a leading space makes the fill a paste (indentation): the field refuses it as it refuses a fill
    await _open(session, REFUSING.replace("LATER", "false"))
    result = await session.aexecute(FillAction(selector="#phone", value=" 415 555 0123"), raise_on_failure=False)
    assert result.success, result.message
    assert await _value(session, "#phone") == "4155550123"


@pytest.mark.asyncio
async def test_a_refused_paste_with_a_tab_fails(session: NotteSession) -> None:
    # a tab cannot be typed into the field (it moves the focus): the paste the field refused fails
    await _open(session, REFUSING_ALL)
    result = await session.aexecute(FillAction(selector="#phone", value="\t4155550123"), raise_on_failure=False)
    assert not result.success
    assert "stayed empty" in result.message


@pytest.mark.asyncio
async def test_a_tab_whose_timers_do_not_run_is_read_as_it_is(
    session: NotteSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Chrome can hold back the timers of a hidden tab: the read after a task does not come.
    never_late = f"(el, late) => late ? new Promise(() => {{}}) : ({execution._TYPED_VALUE})(el, false)"
    monkeypatch.setattr(execution, "_TYPED_VALUE", never_late)
    monkeypatch.setattr(execution, "_LATE_VALUE_READ_S", 0.2)
    await _open(session, PLAIN)
    result = await session.aexecute(FillAction(selector="#input", value="new", timeout=3000), raise_on_failure=False)
    assert result.success, result.message
    assert await _value(session, "#input") == "new"


@pytest.mark.asyncio
async def test_a_field_that_keeps_nothing_fails(session: NotteSession) -> None:
    await _open(session, REFUSING_ALL)
    result = await session.aexecute(FillAction(selector="#phone", value="4155550123"), raise_on_failure=False)
    assert not result.success
    assert "stayed empty" in result.message
    assert await _value(session, "#phone") == ""


@pytest.mark.asyncio
async def test_a_field_too_short_for_the_text_fails(session: NotteSession) -> None:
    await _open(session, PLAIN)
    result = await session.aexecute(FillAction(selector="#short", value="123456"), raise_on_failure=False)
    assert not result.success
    assert "other text" in result.message
    # the typed value is not quoted: it can be a secret
    assert "123456" not in result.message


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("selector", "text"),
    [("#input", "new"), ("#tel", "+1 415 555 0123"), ("#textarea", "two\nlines"), ("#date", "2026-11-15")],
)
async def test_a_field_that_keeps_the_text_is_filled_at_once(session: NotteSession, selector: str, text: str) -> None:
    await _open(session, PLAIN)
    result = await session.aexecute(FillAction(selector=selector, value=text), raise_on_failure=True)
    assert result.success
    assert await _value(session, selector) == text
    assert await _keys(session) == 0


@pytest.mark.asyncio
async def test_contenteditable_number_and_select_are_unchanged(session: NotteSession) -> None:
    await _open(session, PLAIN)
    _ = await session.aexecute(FillAction(selector="#editable", value="new"), raise_on_failure=True)
    assert await session.window.page.locator("#editable").text_content() == "new"
    _ = await session.aexecute(FillAction(selector="#number", value="42"), raise_on_failure=True)
    assert await _value(session, "#number") == "42"
    _ = await session.aexecute(SelectDropdownOptionAction(selector="#select", value="fr"), raise_on_failure=True)
    assert await _value(session, "#select") == "fr"
    assert await _keys(session) == 0
