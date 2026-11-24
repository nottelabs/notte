"""With `dismiss_blocking_dialogs`, a dialog the site opened over the page that blocks a click or fill on a selector
is dismissed through its own controls and the action is retried once (`notte_browser.dialogs`).

`off` (the default): the failure is reported as before and nothing on the page is touched. `close`: a close or decline
control, then Escape, never an accept control. `any`: an accept control when nothing else closes the dialog. The
action's result message says what was dismissed. Each page here records which control was used in
`document.body.dataset`.
"""

import time
from urllib.parse import quote

import pytest
from notte_browser.dialogs import retries_after_dismissal
from notte_browser.session import NotteSession
from notte_core.actions import ClickAction, FillAction
from notte_core.errors import ActionExecutionError
from notte_core.types import DismissBlockingDialogs

# the dialog's controls record themselves and remove the dialog; the page behind it is `inert` while it is shown
DISMISS = (
    "<script>function dismiss(how) { document.body.dataset.dismissed = how;"
    " document.querySelector('[role=dialog]').remove(); document.querySelector('main').inert = false; }</script>"
)
PAGE = '<main inert><input id="q"><button id="go" onclick="document.body.dataset.clicked = 1">Go</button></main>'
BACKDROP = 'style="position:fixed;inset:0;background:rgba(0,0,0,.5)"'
AGREE = "<button onclick=\"dismiss('agree')\">Agree</button>"
CLOSE = '<button aria-label="Close welcome modal" onclick="dismiss(\'close\')">X</button>'
NO_THANKS = "<button onclick=\"dismiss('no thanks')\">No thanks</button>"
LINKS = '<a href="/terms">Terms of Use</a> <a href="/signin">Sign in</a>'
# controls a dismissal never uses: they record a click without closing anything
SIGN_IN_REGISTER = (
    "<button onclick=\"document.body.dataset.pressed = 'sign in'\">Sign in</button>"
    "<button onclick=\"document.body.dataset.pressed = 'register'\">Register</button>"
)

ON: list[DismissBlockingDialogs] = ["close", "any"]
ALL: list[DismissBlockingDialogs] = ["off", "close", "any"]


def _url(html: str) -> str:
    return f"data:text/html,{quote(html)}"


def _dialog(controls: str, *, escape: bool = False, links: str = LINKS, heading: str = "Welcome") -> str:
    on_escape = (
        "<script>document.addEventListener('keydown', e => { if (e.key === 'Escape') dismiss('escape'); });</script>"
        if escape
        else ""
    )
    return _url(
        f'{PAGE}{DISMISS}{on_escape}<div role="dialog" aria-modal="true" {BACKDROP}>'
        f"<h2>{heading}</h2>{links} {controls}</div>"
    )


async def _state(session: NotteSession) -> dict[str, str]:
    return await session.window.page.evaluate(
        "() => ({...document.body.dataset, value: document.querySelector('#q').value})"
    )


@pytest.mark.asyncio
async def test_off_by_default_the_fill_fails_as_before_and_the_dialog_stays() -> None:
    async with NotteSession(headless=True) as session:
        assert session.window.options.dismiss_blocking_dialogs == "off"
        _ = await session.window.page.goto(_dialog(CLOSE + AGREE))
        result = await session.aexecute(
            FillAction(selector="css=#q", value="hello", timeout=3000), raise_on_failure=False
        )
        state = await _state(session)

    assert not result.success
    assert 'The field stayed empty after typing: a dialog covers the element: "Welcome"' in result.message
    assert "then retried once" not in result.message
    assert "blocks the element" not in result.message
    assert state == {"value": ""}


@pytest.mark.parametrize("mode", ON)
@pytest.mark.asyncio
async def test_a_blocked_fill_is_retried_after_the_dialog_is_closed(mode: DismissBlockingDialogs) -> None:
    async with NotteSession(headless=True, dismiss_blocking_dialogs=mode) as session:
        _ = await session.window.page.goto(_dialog(CLOSE + AGREE))
        result = await session.aexecute(
            FillAction(selector="css=#q", value="hello", timeout=3000), raise_on_failure=False
        )
        state = await _state(session)

    assert result.success, result.message
    assert state == {"dismissed": "close", "value": "hello"}
    assert result.message.endswith(
        "Dismissed 1 dialog blocking the element, then retried once: "
        "dialog \"Welcome\" (inert target): closed by its close control 'Close welcome modal'"
    ), result.message


@pytest.mark.parametrize("mode", ON)
@pytest.mark.asyncio
async def test_a_blocked_click_is_retried_after_the_dialog_is_closed(mode: DismissBlockingDialogs) -> None:
    async with NotteSession(headless=True, dismiss_blocking_dialogs=mode) as session:
        _ = await session.window.page.goto(_dialog(CLOSE + AGREE))
        result = await session.aexecute(ClickAction(selector="css=#go", timeout=2000), raise_on_failure=False)
        state = await _state(session)

    assert result.success, result.message
    assert state == {"dismissed": "close", "clicked": "1", "value": ""}
    assert "closed by its close control 'Close welcome modal'" in result.message


@pytest.mark.parametrize(
    ("mode", "controls", "escape", "dismissed", "said"),
    [
        ("close", AGREE + NO_THANKS, True, "no thanks", "declined by its decline control 'No thanks'"),
        ("any", AGREE + NO_THANKS, True, "no thanks", "declined by its decline control 'No thanks'"),
        ("close", AGREE, True, "escape", "closed by Escape"),
        ("any", AGREE, True, "escape", "closed by Escape"),
        ("any", AGREE, False, "agree", "Escape had no effect, accepted by its accept control 'Agree'"),
    ],
    ids=[
        "close: decline before accept",
        "any: decline before accept",
        "close: Escape",
        "any: Escape before accept",
        "any: accept when nothing else closes it",
    ],
)
@pytest.mark.asyncio
async def test_closing_and_declining_come_before_accepting(
    mode: DismissBlockingDialogs, controls: str, escape: bool, dismissed: str, said: str
) -> None:
    async with NotteSession(headless=True, dismiss_blocking_dialogs=mode) as session:
        _ = await session.window.page.goto(_dialog(controls, escape=escape))
        result = await session.aexecute(
            FillAction(selector="css=#q", value="hello", timeout=3000), raise_on_failure=False
        )
        state = await _state(session)

    assert result.success, result.message
    assert state == {"dismissed": dismissed, "value": "hello"}
    assert f'dialog "Welcome" (inert target): {said}' in result.message, result.message


@pytest.mark.asyncio
async def test_close_never_accepts_and_says_only_an_accept_control_is_left() -> None:
    async with NotteSession(headless=True, dismiss_blocking_dialogs="close") as session:
        _ = await session.window.page.goto(_dialog(AGREE))
        result = await session.aexecute(
            FillAction(selector="css=#q", value="hello", timeout=3000), raise_on_failure=False
        )
        state = await _state(session)

    assert not result.success
    # the original failure, then what blocks the element
    assert isinstance(result.exception, ActionExecutionError)
    assert 'The field stayed empty after typing: a dialog covers the element: "Welcome"' in result.message
    assert (
        'A dialog with only an accept control blocks the element: dialog "Welcome" (inert target): Escape had no '
        "effect, still shown: its only other way out is an accept control ('Agree'), which `close` never uses"
    ) in result.message, result.message
    assert state == {"value": ""}


@pytest.mark.asyncio
async def test_close_keeps_a_blocked_click_failed_when_only_accept_would_close_the_dialog() -> None:
    async with NotteSession(headless=True, dismiss_blocking_dialogs="close") as session:
        _ = await session.window.page.goto(_dialog(AGREE))
        result = await session.aexecute(ClickAction(selector="css=#go", timeout=2000), raise_on_failure=False)
        state = await _state(session)

    assert not result.success
    assert "Element is disabled" in result.message
    assert "A dialog with only an accept control blocks the element" in result.message
    assert state == {"value": ""}


@pytest.mark.parametrize("mode", ALL)
@pytest.mark.asyncio
async def test_a_dialog_without_a_known_control_leaves_the_failure_as_it_was(mode: DismissBlockingDialogs) -> None:
    page = _dialog("<button onclick=\"dismiss('continue')\">Continue</button>")
    async with NotteSession(headless=True, dismiss_blocking_dialogs=mode) as session:
        _ = await session.window.page.goto(page)
        result = await session.aexecute(
            FillAction(selector="css=#q", value="hello", timeout=3000), raise_on_failure=False
        )
        state = await _state(session)

    assert not result.success
    assert "The field stayed empty after typing" in result.message
    if mode != "off":
        # Escape was pressed (the page ignores it); the links and the unknown control were not clicked
        assert (
            'A dialog blocks the element and could not be dismissed: dialog "Welcome" (inert target): '
            "Escape had no effect, still shown"
        ) in result.message, result.message
    assert state == {"value": ""}


@pytest.mark.parametrize("mode", ALL)
@pytest.mark.parametrize("kind", ["fill", "click"])
@pytest.mark.asyncio
async def test_sign_in_and_register_are_never_pressed(mode: DismissBlockingDialogs, kind: str) -> None:
    page = _dialog(SIGN_IN_REGISTER, links="")
    action = (
        FillAction(selector="css=#q", value="hello", timeout=3000)
        if kind == "fill"
        else ClickAction(selector="css=#go", timeout=2000)
    )
    async with NotteSession(headless=True, dismiss_blocking_dialogs=mode) as session:
        _ = await session.window.page.goto(page)
        result = await session.aexecute(action, raise_on_failure=False)
        state = await _state(session)

    assert not result.success
    assert state == {"value": ""}


@pytest.mark.timing
@pytest.mark.asyncio
async def test_a_failure_with_no_dialog_is_not_retried() -> None:
    # a field that keeps nothing it is given, with nothing over the page
    page = _url(
        '<input id="q" oninput="this.value = \'\'">'
        '<div role="dialog" style="position:fixed;bottom:0;left:0;width:200px;height:40px">'
        "<button onclick=\"document.body.dataset.dismissed = 'close'\">Close</button></div>"
    )
    async with NotteSession(headless=True, dismiss_blocking_dialogs="any") as session:
        _ = await session.window.page.goto(page)
        started = time.monotonic()
        result = await session.aexecute(
            FillAction(selector="css=#q", value="hello", timeout=3000), raise_on_failure=False
        )
        elapsed = time.monotonic() - started
        state = await session.window.page.evaluate("() => ({...document.body.dataset})")

    assert not result.success
    assert "The field stayed empty after typing" in result.message
    assert "then retried once" not in result.message
    assert "blocks the element" not in result.message
    # the dialog does not block the field: it is left alone
    assert state == {}
    assert elapsed < 3.0


@pytest.mark.parametrize("mode", ON)
@pytest.mark.asyncio
async def test_stacked_dialogs_are_dismissed_in_turn(mode: DismissBlockingDialogs) -> None:
    page = _url(
        '<main inert><input id="q"></main>'
        "<script>function gone(id, how) { document.body.dataset[id] = how; document.getElementById(id).remove();"
        " if (!document.querySelector('[role=dialog]')) document.querySelector('main').inert = false; }</script>"
        f'<div id="first" role="dialog" aria-modal="true" aria-label="Sign in, save money" {BACKDROP}>'
        "<button aria-label=\"Dismiss sign-in info.\" onclick=\"gone('first', 'close')\">X</button></div>"
        f'<div id="second" role="dialog" aria-modal="true" aria-label="Deals are live" {BACKDROP}>'
        "<button aria-label=\"Close sheet\" onclick=\"gone('second', 'close')\">X</button></div>"
    )
    async with NotteSession(headless=True, dismiss_blocking_dialogs=mode) as session:
        _ = await session.window.page.goto(page)
        result = await session.aexecute(
            FillAction(selector="css=#q", value="hello", timeout=3000), raise_on_failure=False
        )
        state = await _state(session)

    assert result.success, result.message
    assert state == {"first": "close", "second": "close", "value": "hello"}
    assert "Dismissed 2 dialogs blocking the element, then retried once: " in result.message
    assert "closed by its close control 'Close sheet'" in result.message
    assert "closed by its close control 'Dismiss sign-in info.'" in result.message


@pytest.mark.asyncio
async def test_a_target_in_a_popover_of_the_page_is_dismissed_without_escape_or_pointer() -> None:
    # the caller opened a picker (role=dialog) whose search box is the target; it closes on Escape and on a pointer
    # press outside it, as the cookie dialog's Accept is. A cookie dialog covers the picker.
    page = _url(
        '<div id="picker" role="dialog" style="position:fixed;top:0;left:0;width:300px;height:200px">'
        '<input id="search"></div>'
        "<script>document.addEventListener('keydown', e => { if (e.key === 'Escape') picker.remove(); });"
        " document.addEventListener('pointerdown', e => { if (!picker.contains(e.target)) picker.remove(); });"
        " document.addEventListener('input', e => { if (document.getElementById('cookies')) e.target.value = ''; });"
        "</script>"
        '<dialog id="cookies" open style="position:fixed;top:0;left:0;width:400px;height:300px;margin:0">'
        "Allow optional cookies? <button>Customize</button>"
        "<button onclick=\"document.body.dataset.dismissed = 'accept'; cookies.remove()\">Accept</button></dialog>"
    )
    async with NotteSession(headless=True, dismiss_blocking_dialogs="any") as session:
        _ = await session.window.page.goto(page)
        result = await session.aexecute(
            FillAction(selector="css=#search", value="EUR", timeout=3000), raise_on_failure=False
        )
        state = await session.window.page.evaluate(
            "() => ({...document.body.dataset, picker: !!document.getElementById('picker'),"
            " value: document.getElementById('search')?.value})"
        )

    assert result.success, result.message
    assert state == {"dismissed": "accept", "picker": True, "value": "EUR"}
    assert "(covered target): accepted by its accept control 'Accept'" in result.message, result.message


@pytest.mark.asyncio
async def test_the_message_does_not_quote_a_dialog_that_shows_the_typed_text() -> None:
    # a page can write what was typed into its own text: the dialog and its controls are not named then
    async with NotteSession(headless=True, dismiss_blocking_dialogs="any") as session:
        _ = await session.window.page.goto(_dialog(CLOSE, heading="Results for hello"))
        result = await session.aexecute(
            FillAction(selector="css=#q", value="hello", timeout=3000), raise_on_failure=False
        )
        state = await _state(session)

    assert result.success, result.message
    assert state == {"dismissed": "close", "value": "hello"}
    assert result.message.endswith(
        "Dismissed 1 dialog blocking the element, then retried once: dialog (inert target): closed by its close control"
    ), result.message


def test_actions_on_observed_elements_are_left_as_they_are() -> None:
    error = ActionExecutionError("I1", "https://example.com", reason="Element is disabled")
    assert not retries_after_dismissal(ClickAction(id="I1"), error)
    assert retries_after_dismissal(ClickAction(selector="css=#go"), error)
    assert not retries_after_dismissal(ClickAction(selector="css=#go"), ValueError("other"))
