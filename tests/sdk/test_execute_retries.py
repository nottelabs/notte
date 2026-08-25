"""`retries=` on RemoteSession.execute: re-run server-reported failures client side."""

import pytest
from notte_core.errors.base import NotteBaseError

from tests.sdk.test_execute_raise_on_failure import ACTION, over_the_wire, remote_session, server_side_result


def test_retries_rerun_until_the_server_reports_success() -> None:
    failed = over_the_wire(server_side_result(exception=None))
    ok = failed.model_copy(update={"success": True, "exception": None, "exception_detail": None})
    session = remote_session(failed)
    session.client.page.execute.side_effect = [failed, failed, ok]  # pyright: ignore[reportAttributeAccessIssue]

    result = session.execute(ACTION, retries=2, retry_delay_ms=0)

    assert result.success is True
    assert session.client.page.execute.call_count == 3  # pyright: ignore[reportAttributeAccessIssue]


def test_retries_exhausted_applies_the_raise_gate() -> None:
    failed = over_the_wire(server_side_result(exception=None))
    session = remote_session(failed)

    with pytest.raises(NotteBaseError):
        _ = session.execute(ACTION, retries=2, retry_delay_ms=0)

    assert session.client.page.execute.call_count == 3  # pyright: ignore[reportAttributeAccessIssue]


def test_retries_exhausted_returns_failed_result_when_not_raising() -> None:
    failed = over_the_wire(server_side_result(exception=None))
    session = remote_session(failed, raise_on_failure=False)

    result = session.execute(ACTION, retries=1, retry_delay_ms=0)

    assert result.success is False
    assert session.client.page.execute.call_count == 2  # pyright: ignore[reportAttributeAccessIssue]
