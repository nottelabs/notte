"""When the page counts as settled after an action (`notte_browser.settle`)."""

from typing import cast
from unittest.mock import AsyncMock, MagicMock

import notte_browser.settle as settle_module
import pytest
from notte_browser.driver import JSHandle, Page, Request
from notte_browser.settle import (
    CAP_MS,
    EXPECT_MS,
    GRACE_MS,
    LONG_GRACE_MS,
    QUIET_MS,
    SETTLE_MS,
    PageSettle,
    SettleState,
    settled,
)


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


@pytest.mark.parametrize("root_at", [None, 1.0, 3.0])
def test_replacement_navigation_keeps_the_initial_request_boundary(
    monkeypatch: pytest.MonkeyPatch, root_at: float | None
) -> None:
    page = MagicMock(spec=Page)
    root = MagicMock(spec=Request)
    redirect = MagicMock(spec=Request)
    for request in (root, redirect):
        request.frame = page.main_frame
        request.resource_type = "document"
        request.is_navigation_request.return_value = True
        request.url = "https://example.com/"
        request.method = "GET"
        request.post_data_buffer = None
    root.redirected_from = None
    redirect.redirected_from = root
    tracker = PageSettle(page, None, tabs=False)
    if root_at is not None:
        monkeypatch.setattr(settle_module.time, "perf_counter", lambda: root_at)
        tracker._request_started(root)  # pyright: ignore[reportPrivateUsage]
    monkeypatch.setattr(settle_module.time, "perf_counter", lambda: 4.0)
    tracker._request_started(redirect)  # pyright: ignore[reportPrivateUsage]
    assert tracker.navigation_requested_after(2.0) is (root_at == 3.0)
    assert not tracker.navigation_requested_after(None)


def test_everything_ends_at_the_cap() -> None:
    assert settled(state(CAP_MS, 5, CAP_MS - 1, in_flight=3, url_changed_ms=CAP_MS - 1))


def test_a_url_change_waits_for_the_new_page_to_render() -> None:
    # pushState, nothing rendered since
    pushed = {"url_changed_ms": 300.0, "last_dom_change_ms": 100.0}
    assert not settled(state(1_000, 100, 300, **pushed))
    assert settled(state(300 + EXPECT_MS, 100, 300, **pushed))
    rendered = {"url_changed_ms": 300.0, "last_dom_change_ms": 320.0}
    assert settled(state(320 + QUIET_MS, 100, 320, **rendered))


@pytest.mark.asyncio
@pytest.mark.parametrize("continuous", [False, True])
async def test_changes_spanning_the_action_keep_the_quiet_window(
    monkeypatch: pytest.MonkeyPatch, continuous: bool
) -> None:
    # The first change predates acted(), while later changes belong to the action.
    samples = (
        [(275, 225), (475, 425), (675, 625), (875, 825), (1075, 1025), (1275, 1225)]
        if continuous
        else [(275, 225), (425, 375), (550, 375), (575, 375)]
    )
    tracker = MagicMock(spec=JSHandle)
    tracker.evaluate = AsyncMock(
        side_effect=[
            {"elapsed": elapsed, "inputAt": None, "first": 10, "last": last, "dom": last, "urlAt": None}
            for elapsed, last in samples
        ]
    )
    monkeypatch.setattr(settle_module.asyncio, "sleep", AsyncMock())
    settle = PageSettle(cast(Page, MagicMock()), cast(JSHandle, tracker), tabs=False)
    settle._began = settle._started + 0.125
    await settle._poll(GRACE_MS)
    assert tracker.evaluate.await_count == len(samples)


def test_a_new_page_is_watched_for_a_while_after_its_load() -> None:
    # 500 ms after its load event, even with nothing happening
    assert not settled(state(LONG_GRACE_MS - 1, at_least_ms=LONG_GRACE_MS))
    assert settled(state(LONG_GRACE_MS, at_least_ms=LONG_GRACE_MS))


def test_a_new_page_waits_for_its_requests_to_be_quiet_for_a_while() -> None:
    # its last request ended 300 ms ago (before the page was tracked again): the next one may be waiting on a
    # CORS preflight, which the browser does not report
    quiet = {"last_request_ms": -300.0, "request_quiet_ms": float(LONG_GRACE_MS)}
    assert not settled(state(GRACE_MS, **quiet))
    assert settled(state(LONG_GRACE_MS - 300, **quiet))
    # without a request quiet time, a request that ended long enough ago is no reason to wait
    assert settled(state(GRACE_MS, last_request_ms=-300.0))
