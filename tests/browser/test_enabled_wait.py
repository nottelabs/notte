"""A click on a control its caller located with a selector waits while the control is disabled.

A script acts on pages that are still getting ready: a form whose controls are disabled until the page hydrates,
a Save button that is disabled until its field is validated. Such a click was refused at once with "Element is
disabled", where a script written for Playwright would have waited for the control.
"""

import time
from typing import cast
from urllib.parse import quote

import notte_browser.execution as execution_module
import pytest
from notte_browser.driver import Locator
from notte_browser.driver import TimeoutError as PlaywrightTimeoutError
from notte_browser.session import NotteSession
from notte_core.actions import ClickAction

# the control is enabled this long after the page loaded
ENABLE_MS = 700
BUTTON = '<button id="go" {attributes} onclick="document.body.dataset.clicked = 1">Save</button>'
DISABLED_BUTTON = BUTTON.format(attributes="disabled")


def _url(html: str) -> str:
    return f"data:text/html,{quote(html)}"


def _enabled_later(html: str, enable: str) -> str:
    return _url(f"{html}<script>setTimeout(() => {{ {enable} }}, {ENABLE_MS});</script>")


@pytest.mark.parametrize(
    ("html", "enable"),
    [
        (DISABLED_BUTTON, "document.querySelector('#go').disabled = false;"),
        (
            BUTTON.format(attributes='aria-disabled="true"'),
            "document.querySelector('#go').setAttribute('aria-disabled', 'false');",
        ),
        (f"<main inert>{BUTTON.format(attributes='')}</main>", "document.querySelector('main').inert = false;"),
    ],
    ids=["disabled", "aria-disabled", "inert ancestor"],
)
@pytest.mark.asyncio
async def test_a_click_waits_for_a_control_enabled_later(html: str, enable: str) -> None:
    async with NotteSession(headless=True) as session:
        _ = await session.window.page.goto(_enabled_later(html, enable))
        result = await session.aexecute(ClickAction(selector="css=#go"), raise_on_failure=False)
        clicked = await session.window.page.evaluate("() => document.body.dataset.clicked")

    assert result.success, result.message
    assert clicked == "1"


@pytest.mark.parametrize("selector", ["#go", "xpath=//button[@id='go']", {"css_selector": "#go"}])
@pytest.mark.asyncio
async def test_each_selector_form_waits_for_the_control(selector: str | dict[str, str]) -> None:
    page = _enabled_later(DISABLED_BUTTON, "document.querySelector('#go').disabled = false;")
    async with NotteSession(headless=True) as session:
        _ = await session.window.page.goto(page)
        result = await session.aexecute(ClickAction(selector=selector), raise_on_failure=False)  # pyright: ignore[reportArgumentType]
        clicked = await session.window.page.evaluate("() => document.body.dataset.clicked")

    assert result.success, result.message
    assert clicked == "1"


@pytest.mark.asyncio
async def test_a_control_that_stays_disabled_is_refused_after_the_wait() -> None:
    async with NotteSession(headless=True) as session:
        _ = await session.window.page.goto(_url(DISABLED_BUTTON))
        started = time.monotonic()
        result = await session.aexecute(ClickAction(selector="css=#go", timeout=1000), raise_on_failure=False)
        elapsed = time.monotonic() - started
        clicked = await session.window.page.evaluate("() => document.body.dataset.clicked")

    assert not result.success
    assert "Element is disabled" in result.message
    assert clicked is None
    # three fifths of the timeout: the rest is held back for the click and its fallback
    assert elapsed >= 0.55


@pytest.mark.asyncio
async def test_a_control_replaced_while_disabled_is_clicked_once_it_is_back() -> None:
    """A page that hydrates can replace the control: the wait follows the selector, not the first element."""
    page = _url(
        f"""{DISABLED_BUTTON}
        <script>
          setTimeout(() => document.querySelector("#go").remove(), 250);
          setTimeout(() => {{
            document.body.insertAdjacentHTML("beforeend", {BUTTON.format(attributes="")!r});
          }}, {ENABLE_MS});
        </script>"""
    )
    async with NotteSession(headless=True) as session:
        _ = await session.window.page.goto(page)
        result = await session.aexecute(ClickAction(selector="css=#go"), raise_on_failure=False)
        clicked = await session.window.page.evaluate("() => document.body.dataset.clicked")

    assert result.success, result.message
    assert clicked == "1"


class _Clock:
    """Stands in for `asyncio` in the action code: time passes only while the wait pauses."""

    def __init__(self) -> None:
        self.now: float = 0.0
        self.pauses: list[float] = []

    def get_running_loop(self) -> "_Clock":
        return self

    def time(self) -> float:
        return self.now

    async def sleep(self, delay: float) -> None:
        self.pauses.append(delay)
        self.now += delay


class _Disabled:
    """A control that is disabled, and says so at once."""

    def __init__(self) -> None:
        self.looks: int = 0

    async def evaluate(self, expression: str, *, timeout: float) -> bool:
        self.looks += 1
        return True


@pytest.mark.asyncio
async def test_the_wait_ends_with_its_share_of_the_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """The wait takes three fifths of the timeout and its last pause is cut to what is left, so the action's own
    timeout does not end it first."""
    clock = _Clock()
    monkeypatch.setattr(execution_module, "asyncio", clock)
    control = _Disabled()
    action = ClickAction(selector="css=#go", timeout=1000)
    budget = execution_module._ActionBudget(deadline=1.0)  # pyright: ignore[reportPrivateUsage]

    disabled = await execution_module._stays_disabled(cast(Locator, control), action, budget)  # pyright: ignore[reportPrivateUsage]

    assert disabled
    assert sum(clock.pauses) == pytest.approx(0.6)
    assert max(clock.pauses) <= 0.1
    assert clock.now <= 0.6 + 1e-9


class _EnabledLater:
    """A control that is disabled at the first look and enabled at the second."""

    def __init__(self) -> None:
        self.looks: int = 0

    async def evaluate(self, expression: str, *, timeout: float) -> bool:
        self.looks += 1
        return self.looks == 1


@pytest.mark.asyncio
async def test_the_wait_ends_as_soon_as_the_control_is_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = _Clock()
    monkeypatch.setattr(execution_module, "asyncio", clock)
    control = _EnabledLater()
    action = ClickAction(selector="css=#go", timeout=1000)
    budget = execution_module._ActionBudget(deadline=1.0)  # pyright: ignore[reportPrivateUsage]

    disabled = await execution_module._stays_disabled(cast(Locator, control), action, budget)  # pyright: ignore[reportPrivateUsage]

    assert not disabled
    assert clock.pauses == [0.1]
    assert control.looks == 2


@pytest.mark.asyncio
async def test_a_lookup_that_used_the_share_leaves_no_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    """The lookup and this wait share the same three fifths: an element found at the end of them is not waited
    for again, so the click keeps its time."""
    clock = _Clock()
    monkeypatch.setattr(execution_module, "asyncio", clock)
    clock.now = 0.6
    action = ClickAction(selector="css=#go", timeout=1000)
    budget = execution_module._ActionBudget(deadline=1.0)  # pyright: ignore[reportPrivateUsage]

    disabled = await execution_module._stays_disabled(cast(Locator, _Disabled()), action, budget)  # pyright: ignore[reportPrivateUsage]

    assert disabled
    # the budget is never 0 (0 means no timeout for the browser): what is left of the share is its floor of 1 ms
    assert clock.pauses == pytest.approx([0.001])


class _Removed:
    """A control that is disabled at first, then taken off the page for good: a look waits for it as long as it
    is allowed to, on the wait's clock, then times out."""

    def __init__(self, clock: _Clock) -> None:
        self.clock: _Clock = clock
        self.timeouts: list[float] = []

    async def evaluate(self, expression: str, *, timeout: float) -> bool:
        self.timeouts.append(timeout)
        if len(self.timeouts) == 1:
            return True
        self.clock.now += timeout / 1000
        raise PlaywrightTimeoutError("the control is not on the page")


@pytest.mark.asyncio
async def test_a_control_taken_off_the_page_does_not_use_the_time_of_the_click(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A look at a control that is gone waits for it until the end of this wait, not of the whole action."""
    clock = _Clock()
    monkeypatch.setattr(execution_module, "asyncio", clock)
    control = _Removed(clock)
    action = ClickAction(selector="css=#go", timeout=1000)
    budget = execution_module._ActionBudget(deadline=1.0)  # pyright: ignore[reportPrivateUsage]

    disabled = await execution_module._stays_disabled(cast(Locator, control), action, budget)  # pyright: ignore[reportPrivateUsage]

    assert disabled
    # the first look has the whole action; the look after the first pause has what is left of the wait
    assert control.timeouts == pytest.approx([1000, 500])
    assert clock.now == pytest.approx(0.6)


@pytest.mark.asyncio
async def test_an_observed_control_is_refused_at_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """An observed element was read from the page as it is: when it is disabled the click is refused, not held."""
    clock = _Clock()
    monkeypatch.setattr(execution_module, "asyncio", clock)
    control = _Disabled()
    action = ClickAction(id="B1", timeout=1000)
    budget = execution_module._ActionBudget(deadline=1.0)  # pyright: ignore[reportPrivateUsage]

    disabled = await execution_module._stays_disabled(cast(Locator, control), action, budget)  # pyright: ignore[reportPrivateUsage]

    assert disabled
    assert clock.pauses == []
    assert control.looks == 1
