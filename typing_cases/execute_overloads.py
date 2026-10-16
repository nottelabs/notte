"""Cases for the generated `execute()` overloads (checked by basedpyright).

Lines ending in `# expect-error` must be reported; every other line must type-check.
Keep this file free of runtime side effects; checkers only need the annotations.
"""

from __future__ import annotations

from notte_browser.session import NotteSession
from notte_core.actions import GotoAction
from notte_sdk.endpoints.sessions import RemoteSession


async def _check_local_session(session: NotteSession) -> None:
    _ = session.execute(GotoAction(url="https://example.com"))
    _ = session.execute(type="goto", url="https://example.com", wait_until="commit")
    _ = session.execute(type="click", selector="#submit", timeout=1000)
    _ = session.execute(type="fill", selector="#email", value="a@b.co", clear_before_fill=False, timeout=5000)
    _ = session.execute(type="multi_factor_fill", id="I1", value="123456")
    _ = await session.aexecute(type="switch_tab", tab_index=0)
    _ = await session.aexecute(type="evaluate_js", code="document.title", raise_on_failure=False)
    _ = session.execute(type="goto", value="https://example.com")  # expect-error
    _ = session.execute(type="fill", selector="#email")  # expect-error
    _ = session.execute(type="scrape")  # expect-error
    _ = await session.aexecute(type="email_read")  # expect-error
    _ = session.execute(type="email_verification_read", mailbox_id="m", sender_domain="example.com")  # expect-error


def _check_remote_session(session: RemoteSession) -> None:
    _ = session.execute(GotoAction(url="https://example.com"))
    _ = session.execute(type="goto", url="https://example.com")
    _ = session.execute(type="fallback_fill", id="I1", value="hello", timeout=5000)
    _ = session.execute(type="email_verification_read", mailbox_id="m", sender_domain="example.com")
    _ = session.execute(type="goto", value="https://example.com")  # expect-error
    _ = session.execute(type="sms_read")  # expect-error
    _ = session.execute(type="help", reason="stuck")  # expect-error
