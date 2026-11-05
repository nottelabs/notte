"""Which action the history says opened the dialog now over the page (`ActHistoryEntry.opened_dialog`)."""

from notte_core.act.runner import NO_VALUE, ActHistory, ActHistoryEntry
from notte_core.act.space import ObservedPage
from notte_core.actions import ClickAction

URL = "https://example.test/socks"
PAGE = """### Content of 'WebArea' component with text 'body content'
_[:]Socks
B1[:]<button>Add to cart</button>"""
DIALOG = """### Content of 'dialog' component with text 'Added to cart'
_[:]Added to cart
B2[:]<button>Checkout</button>"""


def _page(description: str, fingerprint: str) -> ObservedPage:
    return ObservedPage(
        url=URL,
        title="Socks",
        description=description,
        actions=[ClickAction(id="B1", text_label="Add to cart")],
        viewport=None,
        states={},
        fingerprint=fingerprint,
    )


def _act(history: ActHistory, kind: str, fingerprint: str) -> ActHistoryEntry:
    entry = ActHistoryEntry(
        action=kind, kind=kind, text=None, fingerprint=fingerprint, pending=True, source_url=URL, instruction="buy"
    )
    history.entries.append(entry)
    return entry


def test_a_dialog_that_shows_during_a_wait_is_the_result_of_the_action_before_it() -> None:
    # the click's request answers late: the confirmation shows while act waits
    history = ActHistory()
    click = _act(history, "CLICK", "page")
    history.observed(_page(PAGE, "page"))
    assert click.opened_dialog is False
    wait = _act(history, "WAIT", "page")
    history.observed(_page(DIALOG, "dialog"))
    assert click.opened_dialog is True and wait.opened_dialog is False


def test_only_the_last_action_opened_the_dialog_now_over_the_page() -> None:
    # the click opened a dialog; the next action replaced it with another one: the click no longer did
    history = ActHistory()
    click = _act(history, "CLICK", "page")
    history.observed(_page(DIALOG, "dialog"))
    assert click.opened_dialog is True
    decline = _act(history, "CLICK", "dialog")
    decline.dialog_before = True
    history.observed(_page(DIALOG, "dialog2"))
    assert click.opened_dialog is False and decline.opened_dialog is False


def test_a_skipped_field_is_not_said_to_have_opened_a_dialog() -> None:
    # the click opened the dialog; a field the goal gives no value for is skipped (nothing ran); then act waits
    history = ActHistory()
    click = _act(history, "CLICK", "page")
    history.observed(_page(DIALOG, "dialog"))
    history.entries.append(
        ActHistoryEntry(
            action="Gift note",
            kind="TYPE_TEXT",
            text=None,
            fingerprint="dialog",
            page_changed=False,
            pending=False,
            error=NO_VALUE,
        )
    )
    skipped = history.entries[-1]
    wait = _act(history, "WAIT", "dialog")
    wait.dialog_before = True
    history.observed(_page(DIALOG, "dialog"))
    assert skipped.opened_dialog is False and wait.opened_dialog is False
    # the click opened it, and the dialog is still the one over the page
    assert click.opened_dialog is True


def test_a_dialog_that_shows_while_a_field_is_skipped_is_told_on_the_next_decision() -> None:
    # the click's dialog shows while the writer decides it has no value for a field: the observation after the skip
    # (no action ran) tells the click opened it
    history = ActHistory()
    click = _act(history, "CLICK", "page")
    history.observed(_page(PAGE, "page"))
    assert click.opened_dialog is False
    history.entries.append(
        ActHistoryEntry(
            action="Gift note",
            kind="TYPE_TEXT",
            text=None,
            fingerprint="page",
            page_changed=False,
            pending=False,
            error=NO_VALUE,
        )
    )
    history.observed(_page(DIALOG, "dialog"))
    assert click.opened_dialog is True


def test_a_click_whose_navigation_ended_later_did_not_open_the_dialog_on_the_new_page() -> None:
    # the click is first observed on its own page; its navigation ends while a field is skipped, onto a page that
    # shows a dialog of its own
    history = ActHistory()
    click = _act(history, "CLICK", "page")
    history.observed(_page(PAGE, "page"))
    history.entries.append(
        ActHistoryEntry(
            action="Gift note",
            kind="TYPE_TEXT",
            text=None,
            fingerprint="page",
            page_changed=False,
            pending=False,
            error=NO_VALUE,
        )
    )
    from dataclasses import replace

    history.observed(replace(_page(DIALOG, "dialog"), url="https://example.test/cart"))
    assert click.opened_dialog is False
