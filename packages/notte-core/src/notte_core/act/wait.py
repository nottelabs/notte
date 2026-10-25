"""The WAIT of `act()`: wait for the page to change, up to a bound, instead of a fixed delay.

A WAIT is chosen when the needed control is not ready yet (a disabled field, results still loading).
A fixed delay is either too short for slow pages (the decider sees the same page and gives up) or wasted
on fast ones. The page script below returns as soon as the DOM changes and then stays quiet for
`QUIET_MS` (at most `SETTLE_MS` after the first change, for pages that never stop changing), or after
`timeout_ms` without a change, in the page, its same-origin frames or its open shadow roots (up to `MAX_ROOTS`).
Inline `style` changes (animations) do not count. A navigation also ends
the wait (the browser destroys the page script, or the URL changed); the session reports it as a change. Any
other failure of the script is a failed WAIT.

The bound (`WAIT_MS` in `notte_core.act.space`) is 3 s: long enough for the usual asynchronous updates
(a spinner, a debounced search, an XHR that fills a list) to land in one step, short enough that a WAIT
on a page that does not change costs little. The decider observes the page again after each WAIT and
can wait again.
"""

import datetime as dt

from notte_core.actions import WaitAction
from notte_core.errors import ActionExecutionError
from notte_core.observation import ExecutionResult

QUIET_MS = 200
SETTLE_MS = 1_000
# the most documents and shadow roots watched: the page, its same-origin frames and its open shadow roots
MAX_ROOTS = 50

# An expression: the page's document, then its same-origin frames' documents and open shadow roots (nested ones
# too), at most `MAX_ROOTS`. The page scripts that watch the page (WAIT, the settle) observe all of them.
NESTED_ROOTS_JS = f"""(() => {{
    const roots = [document];
    for (let i = 0; i < roots.length && roots.length < {MAX_ROOTS}; i++) {{
        for (const el of roots[i].querySelectorAll("*")) {{
            if (roots.length >= {MAX_ROOTS}) break;
            if (el.shadowRoot) roots.push(el.shadowRoot);
            if (el.tagName === "IFRAME" || el.tagName === "FRAME") {{
                try {{ if (el.contentDocument) roots.push(el.contentDocument); }} catch (e) {{}}
            }}
        }}
    }}
    return roots;
}})()"""

WAIT_FOR_CHANGE_JS = f"""(timeoutMs) => new Promise((resolve) => {{
    let changed = false;
    let quiet = null;
    let settle = null;
    let cap = null;
    let observer = null;
    const done = () => {{
        if (observer) observer.disconnect();
        clearTimeout(quiet);
        clearTimeout(settle);
        clearTimeout(cap);
        resolve(changed ? "changed" : "unchanged");
    }};
    observer = new MutationObserver((mutations) => {{
        if (!mutations.some((m) => m.type !== "attributes" || m.attributeName !== "style")) return;
        changed = true;
        clearTimeout(quiet);
        quiet = setTimeout(done, {QUIET_MS});
        if (settle === null) settle = setTimeout(done, {SETTLE_MS});
    }});
    // act() also targets elements in same-origin frames and open shadow roots: watch them too
    const roots = {NESTED_ROOTS_JS};
    for (const root of roots) {{
        observer.observe(root, {{ subtree: true, childList: true, characterData: true, attributes: true }});
    }}
    cap = setTimeout(done, timeoutMs);
}})"""


# how the browser reports a page script ended by a navigation
_NAVIGATION_ERRORS = ("Execution context was destroyed", "most likely because of a navigation")


def interrupted_by_navigation(error: str, url_before: str | None, url_after: str | None) -> bool:
    """A failed wait script was ended by a navigation (not a script error or a timeout)."""
    if any(marker in error for marker in _NAVIGATION_ERRORS):
        return True
    return url_before is not None and url_after is not None and url_after != url_before


def wait_failure(reason: str, url: str, started: dt.datetime, timeout_ms: int) -> ExecutionResult:
    """The `ExecutionResult` of a WAIT whose page script failed (`reason`: the error)."""
    ended = dt.datetime.now(dt.timezone.utc)
    error = ActionExecutionError(action_id="wait", url=url, reason=reason)
    return ExecutionResult(
        action=WaitAction(time_ms=timeout_ms),
        success=False,
        message=error.dev_message,
        exception=error,
        started_at=started,
        ended_at=ended,
    )


def wait_result(outcome: str, started: dt.datetime, timeout_ms: int) -> ExecutionResult:
    """The `ExecutionResult` of a WAIT that ended with `outcome`: `changed`, `navigated` or `unchanged`."""
    ended = dt.datetime.now(dt.timezone.utc)
    elapsed = round((ended - started).total_seconds() * 1000)
    message = {
        "changed": f"The page changed after {elapsed} ms.",
        "navigated": f"The page navigated after {elapsed} ms.",
    }.get(outcome, f"The page did not change in {timeout_ms} ms.")
    return ExecutionResult(
        action=WaitAction(time_ms=timeout_ms), success=True, message=message, started_at=started, ended_at=ended
    )
