"""Reveal-type cases for evaluate_js overload resolution (checked by basedpyright and ty).

Keep this file free of runtime side effects; checkers only need the annotations.
"""

from __future__ import annotations

from typing import reveal_type

from notte_browser.session import NotteSession
from notte_sdk.endpoints.sessions import RemoteSession


def _check_remote_session(session: RemoteSession) -> None:
    text = session.evaluate_js("1 + 1")
    reveal_type(text)  # str
    envelope = session.evaluate_js("1 + 1", raise_on_failure=False)
    reveal_type(envelope)  # ExecutionResult


def _check_computed_bool(session: RemoteSession, flag: bool) -> None:
    # a non-literal bool matches via argument expansion on both checkers;
    # no plain-bool overload is needed
    either = session.evaluate_js("1 + 1", raise_on_failure=flag)
    reveal_type(either)  # str | ExecutionResult


async def _check_local_session(session: NotteSession) -> None:
    text = await session.aevaluate_js("1 + 1")
    reveal_type(text)  # str
    envelope = await session.aevaluate_js("1 + 1", raise_on_failure=False)
    reveal_type(envelope)  # ExecutionResult
    sync_text = session.evaluate_js("1 + 1")
    reveal_type(sync_text)  # str
    sync_envelope = session.evaluate_js("1 + 1", raise_on_failure=False)
    reveal_type(sync_envelope)  # ExecutionResult
