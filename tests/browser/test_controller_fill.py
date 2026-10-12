from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from notte_browser.session import NotteSession
from notte_core.actions import FallbackFillAction, FillAction, MultiFactorFillAction
from notte_core.credentials.types import ValueWithPlaceholder

PAGE = """
<input id="input" value="Hello">
<input id="email" type="email" value="john">
<textarea id="textarea">Line</textarea>
<div id="editable" contenteditable="true">Rich</div>
<input id="otp" value="000">
<script>
    // Recorded on the DOM: page.evaluate may run in an isolated world that cannot see main-world globals.
    document.addEventListener("paste", (event) => {
        document.body.dataset.pasted = event.clipboardData.getData("text/plain");
    });
</script>
"""


@pytest_asyncio.fixture(loop_scope="function")
async def session() -> AsyncIterator[NotteSession]:
    async with NotteSession(headless=True) as session:
        await session.window.page.set_content(PAGE)
        yield session


async def value_of(session: NotteSession, selector: str) -> str:
    return await session.window.page.locator(selector).input_value()


@pytest.mark.asyncio
@pytest.mark.parametrize("selector", ["#input", "#email", "#textarea"])
async def test_fill_clears_existing_value_by_default(session: NotteSession, selector: str) -> None:
    res = await session.aexecute(FillAction(selector=selector, value="world"), raise_on_failure=True)
    assert res.success
    assert await value_of(session, selector) == "world"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("selector", "expected"), [("#input", "HelloWorld"), ("#email", "john@example.com"), ("#textarea", "LineWorld")]
)
async def test_fill_appends_when_clear_before_fill_is_false(
    session: NotteSession, selector: str, expected: str
) -> None:
    # No leading whitespace: indented values take the paste path (see test_fill_with_tabs_pastes_the_secret_value)
    suffix = "@example.com" if selector == "#email" else "World"
    action = FillAction(selector=selector, value=suffix, clear_before_fill=False)
    res = await session.aexecute(action, raise_on_failure=True)
    assert res.success
    assert await value_of(session, selector) == expected


@pytest.mark.asyncio
async def test_fill_contenteditable_clear_vs_append(session: NotteSession) -> None:
    editable = session.window.page.locator("#editable")

    _ = await session.aexecute(
        FillAction(selector="#editable", value="Text", clear_before_fill=False), raise_on_failure=True
    )
    assert await editable.text_content() == "RichText"

    _ = await session.aexecute(FillAction(selector="#editable", value="Plain"), raise_on_failure=True)
    assert await editable.text_content() == "Plain"


@pytest.mark.asyncio
async def test_fill_with_tabs_pastes_the_secret_value(session: NotteSession) -> None:
    secret = "line1\n\tline2"  # an indented line takes the paste path  # pragma: allowlist secret
    value = ValueWithPlaceholder(secret, "placeholder")
    res = await session.aexecute(FillAction(selector="#textarea", value=value), raise_on_failure=True)
    assert res.success
    assert await session.window.page.locator("body").get_attribute("data-pasted") == secret


@pytest.mark.asyncio
async def test_fallback_fill_clear_vs_append(session: NotteSession) -> None:
    _ = await session.aexecute(
        FallbackFillAction(selector="#input", value="!", clear_before_fill=False), raise_on_failure=True
    )
    assert await value_of(session, "#input") == "Hello!"

    _ = await session.aexecute(FallbackFillAction(selector="#input", value="Bye"), raise_on_failure=True)
    assert await value_of(session, "#input") == "Bye"


@pytest.mark.asyncio
async def test_multi_factor_fill_clear_vs_append(session: NotteSession) -> None:
    _ = await session.aexecute(MultiFactorFillAction(selector="#otp", value="123456"), raise_on_failure=True)
    assert await value_of(session, "#otp") == "123456"

    _ = await session.aexecute(
        MultiFactorFillAction(selector="#otp", value="7", clear_before_fill=False), raise_on_failure=True
    )
    assert (await value_of(session, "#otp")).count("7") == 1
