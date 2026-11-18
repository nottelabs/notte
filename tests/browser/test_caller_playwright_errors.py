"""Playwright refusals caused by the caller's selector, element or value are reported as such, not as internal errors."""

from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from notte_browser.driver import Error
from notte_browser.errors import (
    AmbiguousSelectorError,
    ElementNotFillableError,
    ElementTypeMismatchError,
    InvalidActionTargetError,
    InvalidFillValueError,
    InvalidSelectorError,
    classify_caller_playwright_error,
)
from notte_browser.session import NotteSession
from notte_core.actions import ClickAction, FillAction
from notte_core.errors import ErrorConfig, NotteBaseError
from notte_core.observation import SerializedError

STRICT_MODE = (
    'Locator.evaluate: Error: strict mode violation: locator("text=Accept") resolved to 2 elements:\n'
    '    1) <b>"Accept"</b> aka get_by_text("\\"Accept\\"")\n'
    '    2) <button type="button">Accept</button> aka get_by_role("button", name="Accept")\n\n'
    "Call log:\n"
    '  - waiting for locator("text=Accept")\n'
)


@pytest.mark.parametrize(
    ("detail", "error_type", "user_message"),
    [
        (
            STRICT_MODE,
            AmbiguousSelectorError,
            'The selector locator("text=Accept") matched 2 elements, but an action needs a selector that matches '
            "exactly one element. Make the selector more specific so that it is unique on the page.",
        ),
        (
            'Locator.evaluate: Error: strict mode violation: get_by_role("button", name="Search") resolved to 3 '
            "elements:",
            AmbiguousSelectorError,
            'The selector get_by_role("button", name="Search") matched 3 elements, but an action needs a selector '
            "that matches exactly one element. Make the selector more specific so that it is unique on the page.",
        ),
        (
            'ElementHandle.fill: Error: Input of type "button" cannot be filled\nCall log:\n    - fill("1234")\n',
            ElementNotFillableError,
            'The element the selector matched cannot be filled: it is an input of type "button". Target an '
            "editable <input>, a <textarea> or a [contenteditable] element instead.",
        ),
        (
            "ElementHandle.fill: Error: Element is not an <input>, <textarea> or [contenteditable] element",
            ElementNotFillableError,
            "The element the selector matched cannot be filled: it is not an <input>, <textarea> or "
            "[contenteditable] element. Target an editable <input>, a <textarea> or a [contenteditable] element "
            "instead.",
        ),
        (
            "Locator.fill: Error: Malformed value",
            InvalidFillValueError,
            "The element the selector matched rejected the value: the value does not match the input's format. Use "
            "a value in the input's format (for example YYYY-MM-DD for a date input, digits for a number input).",
        ),
        (
            "Locator.press_sequentially: Error: Cannot type text into input[type=number]",
            InvalidFillValueError,
            "The element the selector matched rejected the value: a number input does not accept text. Use a value "
            "in the input's format (for example YYYY-MM-DD for a date input, digits for a number input).",
        ),
        (
            "Locator.select_option: Error: Element is not a <select> element",
            ElementTypeMismatchError,
            "The element the selector matched does not support this action: it is not a <select> element. Target "
            "another element.",
        ),
        (
            "Locator.check: Error: Not a checkbox or radio button",
            ElementTypeMismatchError,
            "The element the selector matched does not support this action: it is not a checkbox or radio button. "
            "Target another element.",
        ),
        (
            'Locator.evaluate: Unexpected token "/" while parsing css selector "a[href=/x]". Did you mean to '
            "CSS.escape it?",
            InvalidSelectorError,
            'The selector is not valid: Unexpected token "/" while parsing css selector "a[href=/x]". Did you mean '
            "to CSS.escape it? Fix its syntax and try again.",
        ),
        (
            "Locator.click: SyntaxError: Failed to execute 'evaluate' on 'Document': The string '//button[' is not a "
            "valid XPath expression.",
            InvalidSelectorError,
            "The selector is not valid: The string '//button[' is not a valid XPath expression. Fix its syntax and "
            "try again.",
        ),
        (
            'Locator.click: Error: "has-text" engine expects a single string',
            InvalidSelectorError,
            'The selector is not valid: "has-text" engine expects a single string. Fix its syntax and try again.',
        ),
        (
            # the selector quotes another error's text: only Playwright's own diagnostic decides the error
            'Locator.click: Unexpected token "" while parsing css selector "[aria-label="Malformed value"". Did you '
            "mean to CSS.escape it?",
            InvalidSelectorError,
            'The selector is not valid: Unexpected token "" while parsing css selector "[aria-label="Malformed '
            'value"". Did you mean to CSS.escape it? Fix its syntax and try again.',
        ),
    ],
)
def test_caller_errors_are_classified(detail: str, error_type: type[NotteBaseError], user_message: str) -> None:
    error = classify_caller_playwright_error(Error(detail))

    assert isinstance(error, error_type)
    assert error.user_message == user_message
    assert detail in error.dev_message
    assert detail in error.agent_message
    assert not error.should_notify_team
    assert not error.should_retry_later


@pytest.mark.parametrize(
    "detail",
    [
        "Page.wait_for_timeout: Target page, context or browser has been closed",
        "Locator.click: Error: Element is outside of the viewport",
        "net::ERR_CONNECTION_RESET",
        # the call log quotes the filled value, not Playwright's diagnostic
        'Locator.click: Timeout 1000ms exceeded.\nCall log:\n  - waiting for get_by_text("Malformed value")\n',
    ],
)
def test_other_errors_are_not_classified(detail: str) -> None:
    assert classify_caller_playwright_error(Error(detail)) is None


def test_selector_given_by_the_caller_is_named() -> None:
    error = classify_caller_playwright_error(Error(STRICT_MODE), selector="'#results'")

    assert isinstance(error, AmbiguousSelectorError)
    assert error.user_message.startswith("The selector '#results' matched 2 elements")


def test_classified_error_survives_the_wire() -> None:
    error = classify_caller_playwright_error(Error(STRICT_MODE))
    assert error is not None

    rehydrated = SerializedError.from_exception(error).to_exception()

    assert type(rehydrated) is AmbiguousSelectorError
    assert rehydrated.user_message == error.user_message
    assert not rehydrated.should_notify_team


PAGE = """
<p>Click <b>"Accept"</b> to continue.</p>
<button type="button">Accept</button>
<input id="submit" type="button" value="Go">
<span id="label">Name</span>
<div class="result">One</div>
<div class="result">Two</div>
"""


@pytest_asyncio.fixture(loop_scope="function")
async def session() -> AsyncIterator[NotteSession]:
    async with NotteSession(headless=True) as session:
        await session.window.page.set_content(PAGE)
        yield session


@pytest.fixture
def user_messages() -> Iterator[None]:
    # The API serializes `exception` as the user message, so the tests read the error the way callers do.
    with ErrorConfig.message_mode("user"):
        yield


@pytest.mark.asyncio
@pytest.mark.usefixtures("user_messages")
@pytest.mark.parametrize(
    ("action", "error_type", "starts_with"),
    [
        (
            ClickAction(selector="text=Accept"),
            AmbiguousSelectorError,
            'The selector locator("text=Accept") matched 2 elements, but an action needs a selector',
        ),
        (
            FillAction(selector="#submit", value="1234"),
            ElementNotFillableError,
            'The element the selector matched cannot be filled: it is an input of type "button".',
        ),
        (
            FillAction(selector="#label", value="1234"),
            ElementNotFillableError,
            "The element the selector matched cannot be filled: it is not an <input>",
        ),
        (
            ClickAction(selector="xpath=//button["),
            InvalidSelectorError,
            "The selector is not valid: The string '//button[' is not a valid XPath expression.",
        ),
        (
            # the quoted form, button:has-text("Accept"), is the valid one
            ClickAction(selector="button:has-text(Accept)"),
            InvalidSelectorError,
            'The selector is not valid: "has-text" engine expects a single string.',
        ),
    ],
)
async def test_failed_action_names_the_caller_error(
    session: NotteSession, action: ClickAction | FillAction, error_type: type[NotteBaseError], starts_with: str
) -> None:
    res = await session.aexecute(action, raise_on_failure=False)

    assert not res.success
    assert isinstance(res.exception, error_type)
    assert isinstance(res.exception, InvalidActionTargetError)
    assert str(res.exception).startswith(starts_with)
    assert "Our team has been notified" not in str(res.exception)
    assert res.exception_detail is not None
    assert res.exception_detail.error_type == error_type.__name__
    assert not res.exception_detail.should_notify_team


@pytest.mark.asyncio
async def test_scrape_with_ambiguous_selector_names_it(session: NotteSession) -> None:
    with pytest.raises(AmbiguousSelectorError) as raised:
        _ = await session.ascrape(selector=".result", raise_on_failure=True)

    assert raised.value.user_message.startswith("The selector '.result' matched 2 elements")
    assert not raised.value.should_notify_team
