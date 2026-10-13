"""End-to-end checks of the structured exception wire (`ExecutionResult.exception_detail`).

The API serialises failures with `SerializedError` so the client rehydrates the
concrete `NotteBaseError` subclass, its per-audience messages and retry/notify
flags, instead of a bare `NotteBaseError` built from a user-safe string.
"""

import pytest
from notte_core.errors.actions import InvalidActionError
from notte_core.errors.base import NotteBaseError
from notte_sdk.client import NotteClient


def test_failed_action_rehydrates_concrete_exception_over_the_wire():
    client = NotteClient()
    with client.Session(proxies=False, open_viewer=False) as page:
        _ = page.execute(type="goto", value="https://www.example.com")
        _ = page.observe(perception_type="fast")

        # non-raising path: the structured detail crosses the wire and the
        # exception on the result is the concrete class, not the base one
        result = page.execute(type="click", id="B999", raise_on_failure=False)
        assert not result.success
        assert result.exception_detail is not None
        assert result.exception_detail.error_type == "InvalidActionError"
        assert type(result.exception) is InvalidActionError
        assert "B999" in result.exception.dev_message

        # raising path: remote callers catch the same class as local ones,
        # with the action-specific reason intact
        with pytest.raises(InvalidActionError, match="B999"):
            _ = page.execute(type="click", id="B999")

        # evaluate_js failure: the JS reason must reach the caller. Before the
        # eval-js fix is deployed the server reports it without an exception
        # (SDK message fallback); after, as a typed ActionExecutionError. Both
        # are NotteBaseError and both carry the reason.
        with pytest.raises(NotteBaseError, match="JavaScript evaluation failed") as exc_info:
            _ = page.execute(type="evaluate_js", code="notAFunction()")
        assert "notAFunction is not defined" in str(exc_info.value)
