"""The read that killed five deployed marketplace Functions.

Not a hypothetical. `session.execute(type="evaluate_js", ...)` followed by
`result.data.markdown` is what the anything-api builder generated, and these are
the Functions that died on it in production:

    tapology.com          `extraction.data.markdown`
    pokerdb.thehendonmob  `extraction_result.data.markdown`
    carrefour.be          `str(result.data.markdown or "")`
    retailmenot.com       same read
    solebox.com           same read

Their only failure message was `'NoneType' object has no attribute 'markdown'` -
a Python attribute, telling a caller nothing about the site. `.data` is
`DataSpace | None` and is None exactly when the evaluation failed, and the
reason was already sitting unread in `.message`.

The scripts are reduced to the shape that matters, and the page to the markup
that triggers it: a script that assumes the elements it wants are there, and a
page where they are not. That is not a contrived failure - it is what a block
page, an interstitial or a redesign looks like from inside `evaluate_js`, and it
is how at least three of the five actually failed.
"""

import json

import pytest
from notte_browser.session import NotteSession
from notte_core.errors.actions import ActionExecutionError

# Reduced from the real Tapology bout-search script. It reads a property off an
# element it expects to find, which is what every generated extraction script
# does - and what a page that changed, or a block page served in its place, will
# not have. Against such a page this throws inside the browser, which arrives as
# a Playwright error, which used to arrive as a silent `data=None`.
BOUT_SEARCH_SCRIPT: str = """
(() => {
  const heading = document.querySelector("h2.fightCard");
  return JSON.stringify({event: heading.textContent.trim()});
})()
"""

# Stands in for the page the script was not written against. example.com is what
# the other integration tests here load, and it certainly has no `h2.fightCard`.
PAGE_THE_SCRIPT_WAS_NOT_WRITTEN_FOR: str = "https://example.com/"


def tapology_shaped_run(session: NotteSession) -> dict:
    """The generated code, verbatim in shape, down to how it reports failure."""
    try:
        extraction = session.execute(type="evaluate_js", code=BOUT_SEARCH_SCRIPT)
        raw_payload = extraction.data.markdown  # pyright: ignore[reportOptionalMemberAccess]
    except Exception as exc:
        raise RuntimeError(f"Tapology bout search request failed: {exc}") from exc
    return json.loads(raw_payload)


def carrefour_shaped_run(session: NotteSession) -> dict:
    """The `or ""` variant, which reported the wrong cause entirely.

    `str(None or "")` is `""`, so the failure arrived as a JSON parse error and
    sent whoever read it hunting for a malformed response that never existed.
    """
    result = session.execute(type="evaluate_js", code=BOUT_SEARCH_SCRIPT)
    markup = str(result.data.markdown or "")  # pyright: ignore[reportOptionalMemberAccess]
    return json.loads(markup)


def test_a_failed_extraction_names_the_failure_not_the_attribute() -> None:
    """What the caller is told is now about the page, not about Python."""
    with NotteSession(headless=True) as session:
        session.execute(type="goto", url=PAGE_THE_SCRIPT_WAS_NOT_WRITTEN_FOR)

        with pytest.raises(RuntimeError) as raised:
            _ = tapology_shaped_run(session)

    message = str(raised.value)
    assert "JavaScript evaluation failed" in message, message
    # The whole point: this is what the five Functions used to say instead.
    assert "NoneType" not in message, message
    assert "markdown" not in message, message


def test_the_or_empty_string_variant_no_longer_reports_bad_json() -> None:
    """A page that never loaded is not a JSON problem, and no longer says it is.

    The guard has to raise *before* the `or ""` can turn the failure into
    `json.loads("")`, or the caller is told the site returned malformed data.
    """
    with NotteSession(headless=True) as session:
        session.execute(type="goto", url=PAGE_THE_SCRIPT_WAS_NOT_WRITTEN_FOR)

        with pytest.raises(ActionExecutionError) as raised:
            _ = carrefour_shaped_run(session)

    assert not isinstance(raised.value, json.JSONDecodeError)
    assert "JavaScript evaluation failed" in str(raised.value)


def test_opting_out_still_hands_back_the_reason() -> None:
    """`raise_on_failure=False` is the deliberate path, and it has to be usable.

    This is what the builder prompt now teaches: check `.success`, and report
    `.message` - which carries the reason that used to be discarded.
    """
    with NotteSession(headless=True) as session:
        session.execute(type="goto", url=PAGE_THE_SCRIPT_WAS_NOT_WRITTEN_FOR)

        result = session.execute(type="evaluate_js", code=BOUT_SEARCH_SCRIPT, raise_on_failure=False)

    assert result.success is False
    # None here is what `.markdown` was read off. It is the failure, not an
    # empty answer: a successful evaluation always sets `data`, and even a JS
    # `null` arrives as the string "null".
    assert result.data is None
    assert result.message.startswith("JavaScript evaluation failed:")
