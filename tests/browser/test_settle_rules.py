"""When the page counts as settled after an action (`notte_browser.settle`)."""

import pytest
from notte_browser.settle import CAP_MS, EXPECT_MS, GRACE_MS, LONG_GRACE_MS, QUIET_MS, SETTLE_MS, SettleState, settled


def state(elapsed: float, *changes: float, in_flight: int = 0, **fields: float | None) -> SettleState:
    return SettleState(
        elapsed_ms=elapsed,
        first_change_ms=min(changes, default=None),
        last_change_ms=max(changes, default=None),
        in_flight=in_flight,
        **fields,  # pyright: ignore[reportArgumentType]
    )


def test_an_action_without_effect_waits_only_the_grace() -> None:
    assert not settled(state(GRACE_MS - 1))
    assert settled(state(GRACE_MS))
    assert not settled(state(LONG_GRACE_MS - 1, grace_ms=LONG_GRACE_MS))
    assert settled(state(LONG_GRACE_MS, grace_ms=LONG_GRACE_MS))


def test_a_change_needs_a_quiet_page() -> None:
    assert not settled(state(100 + QUIET_MS - 1, 20, 100))
    assert settled(state(100 + QUIET_MS, 20, 100))


def test_a_page_that_keeps_changing_is_left_after_a_while() -> None:
    assert settled(state(10 + SETTLE_MS, 10, 10 + SETTLE_MS - 5))


@pytest.mark.parametrize("elapsed", [GRACE_MS, 1_000, CAP_MS - 1])
def test_a_request_the_action_started_is_waited_for(elapsed: float) -> None:
    assert not settled(state(elapsed, 5, in_flight=1))


def test_everything_ends_at_the_cap() -> None:
    assert settled(state(CAP_MS, 5, CAP_MS - 1, in_flight=3, url_changed_ms=CAP_MS - 1))


def test_a_url_change_waits_for_the_new_page_to_render() -> None:
    # pushState, nothing rendered since
    pushed = {"url_changed_ms": 300.0, "last_dom_change_ms": 100.0}
    assert not settled(state(1_000, 100, 300, **pushed))
    assert settled(state(300 + EXPECT_MS, 100, 300, **pushed))
    rendered = {"url_changed_ms": 300.0, "last_dom_change_ms": 320.0}
    assert settled(state(320 + QUIET_MS, 100, 320, **rendered))
