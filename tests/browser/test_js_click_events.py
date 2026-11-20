"""A click sent from a script (the fallback once the pointer could not click the element) fires the events of a click.

A script clicks a control while a dialog's backdrop covers the page: the pointer click waits for the backdrop to go
away, then the click is sent from the page's script, which was `el.click()`: the click event alone. A widget that
opens on mousedown or pointerdown (a select, a menu, a combobox) did not react to it, the click reported success,
and the next step timed out on an option that never appeared. The script now sends the pointer and mouse events of a
click, in their order, the focus a mousedown gives, then the click and its activation.
"""

from urllib.parse import quote

import pytest
from notte_browser.session import NotteSession
from notte_core.actions import ClickAction

# how long the pointer click waits for the cover to go away before the click is sent from a script
TIMEOUT_MS = 2000
PAGE = """
<style>
  #veil { position: fixed; inset: 0; background: rgba(0, 0, 0, 0.4); }
  #dialog { position: fixed; top: 45%; left: 45%; background: white; padding: 1em; }
</style>
CONTROLS
<div id="veil"></div>
<div id="dialog" role="dialog" aria-label="Consent"><p>We use cookies.</p><button>Accept</button></div>
<script>
  const log = (name) => { const d = document.body.dataset; d[name] = String(Number(d[name] || 0) + 1); };
  for (const type of ["pointerover", "mouseover", "pointerdown", "mousedown", "pointerup", "mouseup", "click"]) {
    document.querySelector("#widget").addEventListener(type, (event) => {
      log(type);
      document.body.dataset.order = (document.body.dataset.order || "") + type[0] + (event.isTrusted ? "T" : "") + " ";
      if (type === "pointerdown") document.body.dataset.x = String(Math.round(event.clientX));
    });
  }
</script>
"""
# a select-like widget: it opens on mousedown (ng-select, react-select) and the option list follows
WIDGET = (
    '<div id="widget" tabindex="TABINDEX" onmousedown="document.body.dataset.opened = 1">Choose a payment option</div>'
)
# a widget that opens on pointerdown and cancels it, so that its compatibility mouse handler does not open it again
POINTER_WIDGET = (
    '<div id="widget" tabindex="0" onpointerdown="event.preventDefault(); document.body.dataset.opened = 1"'
    ' onmousedown="document.body.dataset.opened = 0" onmouseup="document.body.dataset.opened = 0">Menu</div>'
)
# focusable without a tabindex attribute: the first summary of a details element
SUMMARY = '<input id="before" autofocus><details><summary id="widget">Options</summary><p>More</p></details>'
LINK = '<a id="widget" href="javascript:document.body.dataset.went = 1">Go</a>'
SUBMIT = '<form onsubmit="document.body.dataset.sent = 1; return false"><button id="widget">Send</button></form>'


def _url(controls: str) -> str:
    return f"data:text/html,{quote(PAGE.replace('CONTROLS', controls))}"


async def _click(session: NotteSession, controls: str) -> tuple[bool, str, dict[str, str], str]:
    _ = await session.window.page.goto(_url(controls))
    result = await session.aexecute(ClickAction(selector="css=#widget", timeout=TIMEOUT_MS), raise_on_failure=False)
    data = await session.window.page.evaluate("() => ({...document.body.dataset})")
    active = await session.window.page.evaluate("() => document.activeElement && document.activeElement.id")
    return result.success, result.message, data, active


@pytest.mark.asyncio
async def test_a_click_through_a_cover_focuses_an_element_focusable_without_a_tabindex() -> None:
    async with NotteSession(headless=True) as session:
        success, message, data, active = await _click(session, SUMMARY)
        opened = await session.window.page.evaluate("() => document.querySelector('details').open")

    assert success, message
    assert data.get("order") == "p m p m p m c "
    # the focus leaves the field that had it, and the click's activation opens the details
    assert active == "widget"
    assert opened is True


# a tabindex of any value makes the element focusable by a click; -1 only keeps it out of the Tab order
@pytest.mark.parametrize("tabindex", ["0", "-1"])
@pytest.mark.asyncio
async def test_a_click_through_a_cover_opens_a_widget_that_listens_on_mousedown(tabindex: str) -> None:
    widget = WIDGET.replace("TABINDEX", tabindex)
    async with NotteSession(headless=True) as session:
        success, message, data, active = await _click(session, widget)

    assert success, message
    assert data.get("opened") == "1"
    # the events of one click, in their order, each once; the pointer never reached the element
    assert data.get("order") == "p m p m p m c "
    assert {data.get(name) for name in ("pointerdown", "mousedown", "pointerup", "mouseup", "click")} == {"1"}
    # a mousedown gives the focus
    assert active == "widget"
    # the events land where the pointer would have: the element's center
    x = await _center_x(session_html=widget)
    assert abs(int(data["x"]) - x) <= 1


@pytest.mark.asyncio
async def test_a_canceled_pointerdown_suppresses_the_mouse_events() -> None:
    """As a pointer does: a canceled pointerdown keeps the mousedown and mouseup from firing (so the widget is not
    toggled twice) and leaves the focus where it was, while the pointerup and the click still fire."""
    async with NotteSession(headless=True) as session:
        success, message, data, active = await _click(session, POINTER_WIDGET)

    assert success, message
    assert data.get("opened") == "1"
    assert data.get("order") == "p m p p c "
    assert data.get("mousedown") is None
    assert data.get("mouseup") is None
    assert active != "widget"


async def _center_x(session_html: str) -> int:
    async with NotteSession(headless=True) as session:
        _ = await session.window.page.goto(_url(session_html))
        return round(
            await session.window.page.evaluate(
                "() => { const r = document.querySelector('#widget').getBoundingClientRect(); return r.left + r.width / 2 }"
            )
        )


@pytest.mark.parametrize(("controls", "mark"), [(LINK, "went"), (SUBMIT, "sent")], ids=["link", "submit"])
@pytest.mark.asyncio
async def test_a_click_through_a_cover_keeps_the_element_s_activation(controls: str, mark: str) -> None:
    """A link is followed and a form submitted by the click itself, with or without a handler."""
    async with NotteSession(headless=True) as session:
        success, message, data, _ = await _click(session, controls)

    assert success, message
    assert data.get(mark) == "1", data
    assert data.get("click") == "1"
