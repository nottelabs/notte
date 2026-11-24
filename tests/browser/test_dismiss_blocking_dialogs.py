"""With `dismiss_blocking_dialogs`, a dialog the site opened over the page that blocks a click or fill on a selector
is dismissed through its own controls and the action is retried once (`notte_browser.dialogs`).

Off (the default): the failure is reported as before and nothing on the page is touched. On: a close or decline
control, then Escape, then an accept control when nothing else closes the dialog. The action's result message says
what was dismissed. Each page here records which control was used in `document.body.dataset`.
"""

import time
from urllib.parse import quote

import pytest
from notte_browser.dialogs import retries_after_dismissal
from notte_browser.session import NotteSession
from notte_core.actions import ClickAction, FillAction
from notte_core.errors import ActionExecutionError, NotteTimeoutError

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
        assert session.window.options.dismiss_blocking_dialogs is False
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


@pytest.mark.asyncio
async def test_a_blocked_fill_is_retried_after_the_dialog_is_closed() -> None:
    async with NotteSession(headless=True, dismiss_blocking_dialogs=True) as session:
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


@pytest.mark.asyncio
async def test_a_blocked_click_is_retried_after_the_dialog_is_closed() -> None:
    async with NotteSession(headless=True, dismiss_blocking_dialogs=True) as session:
        _ = await session.window.page.goto(_dialog(CLOSE + AGREE))
        result = await session.aexecute(ClickAction(selector="css=#go", timeout=2000), raise_on_failure=False)
        state = await _state(session)

    assert result.success, result.message
    assert state == {"dismissed": "close", "clicked": "1", "value": ""}
    assert "closed by its close control 'Close welcome modal'" in result.message


@pytest.mark.parametrize(
    ("controls", "escape", "dismissed", "said"),
    [
        (AGREE + NO_THANKS, True, "no thanks", "declined by its decline control 'No thanks'"),
        (AGREE, True, "escape", "closed by Escape"),
        (AGREE, False, "agree", "Escape had no effect, accepted by its accept control 'Agree'"),
    ],
    ids=["decline before accept", "Escape before accept", "accept when nothing else closes it"],
)
@pytest.mark.asyncio
async def test_closing_and_declining_come_before_accepting(
    controls: str, escape: bool, dismissed: str, said: str
) -> None:
    async with NotteSession(headless=True, dismiss_blocking_dialogs=True) as session:
        _ = await session.window.page.goto(_dialog(controls, escape=escape))
        result = await session.aexecute(
            FillAction(selector="css=#q", value="hello", timeout=3000), raise_on_failure=False
        )
        state = await _state(session)

    assert result.success, result.message
    assert state == {"dismissed": dismissed, "value": "hello"}
    assert f'dialog "Welcome" (inert target): {said}' in result.message, result.message


@pytest.mark.parametrize("on", [False, True])
@pytest.mark.asyncio
async def test_a_dialog_without_a_known_control_leaves_the_failure_as_it_was(on: bool) -> None:
    page = _dialog("<button onclick=\"dismiss('continue')\">Continue</button>")
    async with NotteSession(headless=True, dismiss_blocking_dialogs=on) as session:
        _ = await session.window.page.goto(page)
        result = await session.aexecute(
            FillAction(selector="css=#q", value="hello", timeout=3000), raise_on_failure=False
        )
        state = await _state(session)

    assert not result.success
    assert "The field stayed empty after typing" in result.message
    if on:
        # Escape was pressed (the page ignores it); the links and the unknown control were not clicked
        assert (
            'A dialog blocks the element and could not be dismissed: dialog "Welcome" (inert target): '
            "Escape had no effect, still shown"
        ) in result.message, result.message
    assert state == {"value": ""}


@pytest.mark.parametrize("on", [False, True])
@pytest.mark.parametrize("kind", ["fill", "click"])
@pytest.mark.asyncio
async def test_sign_in_and_register_are_never_pressed(on: bool, kind: str) -> None:
    page = _dialog(SIGN_IN_REGISTER, links="")
    action = (
        FillAction(selector="css=#q", value="hello", timeout=3000)
        if kind == "fill"
        else ClickAction(selector="css=#go", timeout=2000)
    )
    async with NotteSession(headless=True, dismiss_blocking_dialogs=on) as session:
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
    async with NotteSession(headless=True, dismiss_blocking_dialogs=True) as session:
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


@pytest.mark.asyncio
async def test_stacked_dialogs_are_dismissed_in_turn() -> None:
    page = _url(
        '<main inert><input id="q"></main>'
        "<script>function gone(id, how) { document.body.dataset[id] = how; document.getElementById(id).remove();"
        " if (!document.querySelector('[role=dialog]')) document.querySelector('main').inert = false; }</script>"
        f'<div id="first" role="dialog" aria-modal="true" aria-label="Sign in, save money" {BACKDROP}>'
        "<button aria-label=\"Dismiss sign-in info.\" onclick=\"gone('first', 'close')\">X</button></div>"
        f'<div id="second" role="dialog" aria-modal="true" aria-label="Deals are live" {BACKDROP}>'
        "<button aria-label=\"Close sheet\" onclick=\"gone('second', 'close')\">X</button></div>"
    )
    async with NotteSession(headless=True, dismiss_blocking_dialogs=True) as session:
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
    async with NotteSession(headless=True, dismiss_blocking_dialogs=True) as session:
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
    async with NotteSession(headless=True, dismiss_blocking_dialogs=True) as session:
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


@pytest.mark.parametrize(
    ("controls", "pressed"),
    [
        # a link that leads to another page is not a control, whatever its name
        ('<a href="https://example.com/next">Close</a>', None),
        # named for signing in: not a close control
        ("<button onclick=\"document.body.dataset.pressed = 'sign in'\">Sign in to close</button>", None),
        ("<button onclick=\"document.body.dataset.pressed = 'sign in'\">Close and sign in</button>", None),
        # a close control whose name holds a joining word and a word of the deny list, without going on to it
        ("<button onclick=\"dismiss('close terms')\">Close Terms and Conditions</button>", "close terms"),
        # a link inside the page is still a link
        ('<a href="#details" onclick="document.body.dataset.pressed = \'link\'">Close</a>', None),
        # accepting comes last, also when its name ends with closing: Escape closes this dialog first
        ("<button onclick=\"dismiss('accept and close')\">Accept and close</button>", "escape"),
        ("<button onclick=\"dismiss('agree and close')\">Agree and close</button>", "escape"),
        ("<button onclick=\"dismiss('accept all and close')\">Accept all and close</button>", "escape"),
    ],
    ids=[
        "a link named Close",
        "sign in to close",
        "close and sign in",
        "close terms and conditions",
        "a link inside the page",
        "accept and close",
        "agree and close",
        "accept all and close",
    ],
)
@pytest.mark.asyncio
async def test_a_control_is_read_by_what_it_does_before_the_word_close(controls: str, pressed: str | None) -> None:
    async with NotteSession(headless=True, dismiss_blocking_dialogs=True) as session:
        _ = await session.window.page.goto(_dialog(controls, escape=pressed == "escape", links=""))
        result = await session.aexecute(
            FillAction(selector="css=#q", value="hello", timeout=3000), raise_on_failure=False
        )
        url = session.window.page.url
        state = await _state(session)

    assert url.startswith("data:")
    assert result.success == (pressed is not None), result.message
    assert state == ({"dismissed": pressed, "value": "hello"} if pressed else {"value": ""})


@pytest.mark.asyncio
async def test_every_close_and_decline_control_is_tried_before_accepting() -> None:
    # the first close control does nothing; the page ignores Escape; "Reject all" works
    dead = '<button aria-label="Close" onclick="document.body.dataset.dead = 1">X</button>'
    reject = "<button onclick=\"dismiss('reject all')\">Reject all</button>"
    async with NotteSession(headless=True, dismiss_blocking_dialogs=True) as session:
        _ = await session.window.page.goto(_dialog(dead + AGREE + reject))
        result = await session.aexecute(
            FillAction(selector="css=#q", value="hello", timeout=3000), raise_on_failure=False
        )
        state = await _state(session)

    assert result.success, result.message
    assert state == {"dead": "1", "dismissed": "reject all", "value": "hello"}
    assert "its close control 'Close' had no effect, declined by its decline control 'Reject all'" in result.message


@pytest.mark.asyncio
async def test_a_control_the_page_rebuilt_does_not_end_the_dismissal() -> None:
    # the first close control does nothing but rebuild the footer: the next control found earlier is gone
    rebuild = (
        '<span id="footer"><button aria-label="Close" onclick="footer.innerHTML = footer.innerHTML">X</button>'
        "<button>Reject all</button></span>"
    )
    async with NotteSession(headless=True, dismiss_blocking_dialogs=True) as session:
        _ = await session.window.page.goto(_dialog(rebuild, escape=True))
        result = await session.aexecute(
            FillAction(selector="css=#q", value="hello", timeout=3000), raise_on_failure=False
        )
        state = await _state(session)

    assert result.success, result.message
    assert state == {"dismissed": "escape", "value": "hello"}
    assert (
        "its close control 'Close' had no effect, its decline control 'Reject all' had no effect, closed by Escape"
    ) in result.message, result.message


@pytest.mark.asyncio
async def test_a_dialog_that_shows_the_typed_text_past_its_first_words_is_not_quoted() -> None:
    # no heading: the label is the dialog's first words, cut inside the typed text
    words = "Before you go on, here is what you searched for last time: hello world"
    page = _url(
        f'{PAGE}{DISMISS}<div role="dialog" aria-modal="true" {BACKDROP}><p>{words}</p>'
        '<button aria-label="Close welcome modal" onclick="dismiss(\'close\')">X</button></div>'
    )
    async with NotteSession(headless=True, dismiss_blocking_dialogs=True) as session:
        _ = await session.window.page.goto(page)
        result = await session.aexecute(
            FillAction(selector="css=#q", value="hello world", timeout=3000), raise_on_failure=False
        )

    assert result.success, result.message
    assert result.message.endswith(
        "Dismissed 1 dialog blocking the element, then retried once: dialog (inert target): closed by its close control"
    ), result.message


@pytest.mark.asyncio
async def test_a_banner_over_the_element_and_another_dialog_on_the_page_are_left_alone() -> None:
    # a sticky banner covers the field (it is no dialog), and a chat panel with a dialog role is shown elsewhere
    page = _url(
        '<input id="q" oninput="this.value = \'\'">'
        '<div style="position:fixed;top:0;left:0;width:100%;height:80px">'
        "<button onclick=\"document.body.dataset.pressed = 'banner'\">Close</button></div>"
        '<div role="dialog" aria-label="Chat" style="position:fixed;bottom:0;right:0;width:200px;height:40px">'
        "<button onclick=\"document.body.dataset.pressed = 'chat'\">Close</button></div>"
    )
    async with NotteSession(headless=True, dismiss_blocking_dialogs=True) as session:
        _ = await session.window.page.goto(page)
        result = await session.aexecute(
            FillAction(selector="css=#q", value="hello", timeout=3000), raise_on_failure=False
        )
        state = await session.window.page.evaluate("() => ({...document.body.dataset})")

    assert not result.success
    assert "then retried once" not in result.message
    assert state == {}


@pytest.mark.asyncio
async def test_a_retry_that_fails_still_says_what_was_dismissed() -> None:
    # closing the dialog replaces the field with an element that takes no text: the retried fill fails in the driver
    page = _url(
        '<main inert><input id="q"></main>'
        "<script>function swap() { document.querySelector('[role=dialog]').remove();"
        " document.querySelector('main').outerHTML = '<main><div id=\"q\">closed</div></main>'; }</script>"
        f'<div role="dialog" aria-modal="true" {BACKDROP}><h2>Welcome</h2>'
        '<button aria-label="Close welcome modal" onclick="swap()">X</button></div>'
    )
    async with NotteSession(headless=True, dismiss_blocking_dialogs=True) as session:
        _ = await session.window.page.goto(page)
        result = await session.aexecute(
            FillAction(selector="css=#q", value="hello", timeout=3000), raise_on_failure=False
        )

    assert not result.success
    assert "Dismissed 1 dialog blocking the element, then retried once" in result.message, result.message


def test_only_a_failure_that_names_a_dialog_on_a_selector_is_retried() -> None:
    url = "https://example.com"
    blocked = ActionExecutionError("I1", url, reason='Element is disabled: a dialog covers the element: "Welcome"')
    assert retries_after_dismissal(ClickAction(selector="css=#go"), blocked)
    # an observed element is left as it is
    assert not retries_after_dismissal(ClickAction(id="I1"), blocked)
    # nothing, or something that is no dialog, is in the way
    assert not retries_after_dismissal(
        ClickAction(selector="css=#go"), ActionExecutionError("I1", url, reason="Element is disabled")
    )
    # a timeout: the action may have reached the page before it
    timed_out = NotteTimeoutError(message='Action timed out after 2000ms: a dialog covers the element: "Welcome"')
    assert not retries_after_dismissal(ClickAction(selector="css=#go"), timed_out)
