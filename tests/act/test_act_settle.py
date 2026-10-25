"""When the page counts as settled after an `act()` action that types into an autocomplete field
(`notte_core.act.settle`; the other rules are `notte_browser.settle`'s)."""

from notte_browser.settle import EXPECT_MS, SettleState, settled


def state(elapsed: float, *changes: float, expected: bool | None) -> SettleState:
    return SettleState(
        elapsed_ms=elapsed,
        first_change_ms=min(changes, default=None),
        last_change_ms=max(changes, default=None),
        in_flight=0,
        expected=expected,
    )


def test_typing_into_an_autocomplete_field_waits_for_its_suggestions() -> None:
    # the field re-rendered right away, the suggestions come after a debounce
    assert not settled(state(500, 5, expected=False))
    assert settled(state(500, 5, expected=True))
    # no suggestion for that text
    assert settled(state(EXPECT_MS, 5, expected=False))
