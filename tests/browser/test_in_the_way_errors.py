"""A failed click or fill on a selector says what is in the element's way.

A dialog the site opens (consent, terms, sign-in, promo) covers or disables the element a script acts on. The
action then failed with "The field stayed empty after typing", "Element is disabled" or "Action timed out", and
nothing said that a dialog was in the way. The failure now names it: `a dialog covers the element: "<name>"`.
Which actions succeed does not change: the look only runs once an action has failed.
"""

import asyncio
from urllib.parse import quote

import notte_browser.execution as execution_module
import pytest
from notte_browser.session import NotteSession
from notte_core.actions import ClickAction, FillAction
from notte_core.credentials.types import ValueWithPlaceholder
from notte_core.errors import ActionExecutionError, TextNotKeptError

# the page: a field and a button, both in a part the dialog made inert, as a page does behind a modal dialog
FORM = """
<main id="main" {inert}>
  <input id="q" placeholder="Search">
  <button id="go" onclick="document.body.dataset.clicked = 1">Go</button>
</main>
"""
# a dialog with a backdrop over the whole page, as sites build them
STYLE = """
<style>
  .backdrop { position: fixed; inset: 0; background: rgba(0, 0, 0, .5); }
  .dialog { position: fixed; top: 100px; left: 100px; width: 300px; padding: 20px; background: white; }
</style>
"""
LABELLED = """
<div class="backdrop"><div class="dialog" role="dialog" aria-modal="true" aria-label="Sign in to continue">
  <p>Save 10% with a free membership</p><button>Dismiss</button>
</div></div>
"""
LABELLED_BY = """
<div class="backdrop"><div class="dialog" role="dialog" aria-modal="true" aria-labelledby="title">
  <p id="title">Join the newsletter</p><button>Dismiss</button>
</div></div>
"""
WITH_HEADING = """
<div class="backdrop"><div class="dialog" role="dialog" aria-modal="true">
  <h2>Legal Terms and Privacy</h2><p>By clicking Agree you agree to the Terms of Use.</p><a role="button">Agree</a>
</div></div>
"""
TEXT_ONLY = """
<div class="backdrop"><div class="dialog" role="dialog" aria-modal="true">
  <p>We and our partners use cookies to personalize content and ads, measure traffic and more.</p>
  <button>Accept</button>
</div></div>
"""
# a native modal dialog: the rest of the page is blocked without an `inert` attribute
NATIVE = """
<dialog id="terms"><h2>Allow optional cookies?</h2><button>Accept</button></dialog>
<script>document.getElementById('terms').showModal()</script>
"""
# a banner without a dialog role over the field
BANNER = """
<div id="cookie-banner" class="backdrop">This site uses cookies to improve your experience.</div>
"""
# a dialog in a shadow root (styled there: the document's styles do not reach it), labelled by an element of that
# root, while the document has an element with the same id
SHADOW_LABELLED_BY = (
    """
<p id="title">Our latest offers</p>
<x-modal></x-modal>
<script>
  const root = document.querySelector('x-modal').attachShadow({ mode: 'open' });
  root.innerHTML = `"""
    + STYLE
    + """<div class="backdrop"><div class="dialog" role="dialog" aria-modal="true"
    aria-labelledby="title"><p id="title">Verify your age</p><button>Dismiss</button></div></div>`;
</script>
"""
)
# a background layer behind the page, as a layout with a full-page backdrop image has; the main part sits over it
BACKGROUND = """
<style>#bg { position: fixed; inset: 0; background: #eee } #main { position: relative; z-index: 1 }</style>
<div id="bg">Background layer</div>
"""
# a native modal dialog inside a part the page made inert: the dialog escapes the inertness and takes input
MODAL_IN_INERT = """
<div inert><dialog id="d"><input id="q" oninput="this.value = ''"><button>Save</button></dialog></div>
<script>document.getElementById('d').showModal()</script>
"""
# a field that keeps nothing, with nothing in its way
REFUSING = """<input id="q" oninput="this.value = ''">"""
# a page that answers the look at what is in the way only after the action's deadline
SLOW_LOOK = "(el) => new Promise((resolve) => setTimeout(() => resolve(null), 3000))"


def _url(*parts: str) -> str:
    return f"data:text/html,{quote(''.join(parts))}"


async def _fill(session: NotteSession, page: str) -> str:
    _ = await session.window.page.goto(page)
    result = await session.aexecute(FillAction(selector="#q", value="Lisbon", timeout=3000), raise_on_failure=False)
    assert not result.success
    return result.message


@pytest.mark.parametrize(
    ("dialog", "name"),
    [
        (LABELLED, "Sign in to continue"),
        (LABELLED_BY, "Join the newsletter"),
        (WITH_HEADING, "Legal Terms and Privacy"),
        (TEXT_ONLY, "We and our partners use cookies to personalize..."),
    ],
    ids=["aria-label", "aria-labelledby", "heading", "first words"],
)
@pytest.mark.asyncio
async def test_a_fill_that_stays_empty_names_the_dialog_over_the_field(dialog: str, name: str) -> None:
    async with NotteSession(headless=True) as session:
        message = await _fill(session, _url(STYLE, FORM.format(inert="inert"), dialog))
    assert f'The field stayed empty after typing: a dialog covers the element: "{name}"' in message


# a dialog that shows what was typed into the field behind it, as a suggestions panel or a page that logs input does
ECHOING = """
<div class="backdrop"><div class="dialog" role="dialog" aria-modal="true"><p id="echo">Results for</p></div></div>
<script>
  let longest = "";
  document.addEventListener("input", (event) => {
    // the longest text the field held: it is set at once, then typed key by key
    if (event.target.value.length > longest.length) longest = event.target.value;
    document.getElementById("echo").textContent = "Results for " + longest;
    event.target.value = "";
  }, true);
</script>
"""


@pytest.mark.asyncio
async def test_a_credential_fill_does_not_quote_the_page() -> None:
    """A page can write what was typed into its own text: the message of a fill that typed a credential names no
    page text at all, whatever the dialog says."""
    secret = ValueWithPlaceholder("hunter2-s3cret", "<password>")
    async with NotteSession(headless=True) as session:
        _ = await session.window.page.goto(_url(STYLE, FORM.format(inert=""), ECHOING))
        result = await session.aexecute(FillAction(selector="#q", value=secret, timeout=3000), raise_on_failure=False)
        shown = await session.window.page.locator("#echo").text_content()

    assert not result.success
    # the page did show the credential, and the message has none of it
    assert shown is not None and "hunter2-s3cret" in shown
    assert "The field stayed empty after typing: a dialog covers the element" in result.message
    assert "hunter2" not in result.message
    assert "Results for" not in result.message


@pytest.mark.asyncio
async def test_a_dialog_that_shows_the_typed_text_is_not_quoted() -> None:
    async with NotteSession(headless=True) as session:
        message = await _fill(session, _url(STYLE, FORM.format(inert=""), ECHOING))

    assert "The field stayed empty after typing: a dialog covers the element" in message
    assert "Lisbon" not in message
    assert "Results for" not in message


# a panel with the role of a dialog that is not modal and covers nothing, beside a part the page made inert
SIDE_PANEL = """
<div role="dialog" aria-label="Chat with us" style="position: fixed; right: 0; bottom: 0; width: 200px; height: 100px">
  <p>How can we help?</p>
</div>
"""


@pytest.mark.asyncio
async def test_a_dialog_that_is_not_modal_is_not_named_for_an_inert_field() -> None:
    async with NotteSession(headless=True) as session:
        message = await _fill(session, _url(FORM.format(inert="inert"), SIDE_PANEL))

    assert "The field stayed empty after typing: the element is inert" in message
    assert "Chat with us" not in message


@pytest.mark.asyncio
async def test_a_fill_behind_a_native_modal_dialog_names_it() -> None:
    async with NotteSession(headless=True) as session:
        message = await _fill(session, _url(FORM.format(inert=""), NATIVE))
    assert 'a dialog covers the element: "Allow optional cookies?"' in message


@pytest.mark.asyncio
async def test_a_dialog_in_a_shadow_root_is_named_by_the_label_of_its_own_root() -> None:
    """`aria-labelledby` refers to ids of the dialog's own tree: the document's element with the same id is another
    element."""
    async with NotteSession(headless=True) as session:
        message = await _fill(session, _url(FORM.format(inert="inert"), SHADOW_LABELLED_BY))
    assert 'a dialog covers the element: "Verify your age"' in message


@pytest.mark.asyncio
async def test_a_fill_in_an_inert_part_with_no_dialog_shown_says_so() -> None:
    async with NotteSession(headless=True) as session:
        message = await _fill(session, _url(FORM.format(inert="inert")))
    assert "The field stayed empty after typing: the element is inert" in message


@pytest.mark.asyncio
async def test_a_fill_in_an_inert_part_over_a_background_does_not_name_the_background() -> None:
    """The hit test skips an inert element and returns what is behind it: that is not in the element's way."""
    async with NotteSession(headless=True) as session:
        message = await _fill(session, _url(BACKGROUND, FORM.format(inert="inert")))
    assert message.endswith("The field stayed empty after typing: the element is inert")


@pytest.mark.asyncio
async def test_a_fill_in_a_modal_dialog_inside_an_inert_part_is_not_called_inert() -> None:
    """A modal dialog escapes the inertness of its ancestors: a field in it takes input, and a fill it refuses keeps
    its message."""
    async with NotteSession(headless=True) as session:
        message = await _fill(session, _url(MODAL_IN_INERT))
    assert message.endswith("The field stayed empty after typing")


@pytest.mark.asyncio
async def test_a_fill_that_a_field_refuses_keeps_its_message() -> None:
    async with NotteSession(headless=True) as session:
        message = await _fill(session, _url(REFUSING))
    assert message.endswith("The field stayed empty after typing")


@pytest.mark.parametrize(
    ("page", "action", "error", "reason"),
    [
        (
            REFUSING,
            FillAction(selector="#q", value="Lisbon", timeout=2000),
            TextNotKeptError,
            "The field stayed empty after typing",
        ),
        (
            '<button id="go" disabled>Go</button>',
            ClickAction(selector="#go", timeout=1000),
            ActionExecutionError,
            "Element is disabled",
        ),
    ],
    ids=["fill", "click"],
)
@pytest.mark.asyncio
async def test_a_look_that_outlasts_the_action_deadline_keeps_the_failure(
    monkeypatch: pytest.MonkeyPatch, page: str, action: FillAction | ClickAction, error: type[Exception], reason: str
) -> None:
    """The look at what is in the way runs once the action's timeout no longer applies: a page that answers it
    slowly cannot turn the failure into a timeout. The look's own bound is widened here so that the page's answer,
    not the bound, ends it: a fill typed key by key up to the deadline leaves less than the bound."""
    monkeypatch.setattr(execution_module, "_IN_THE_WAY", SLOW_LOOK)
    monkeypatch.setattr(execution_module, "_IN_THE_WAY_S", 10.0)
    async with NotteSession(headless=True) as session:
        _ = await session.window.page.goto(_url(page))
        result = await session.aexecute(action, raise_on_failure=False)
    assert not result.success
    assert isinstance(result.exception, error), result.message
    assert result.message.endswith(reason)


@pytest.mark.asyncio
async def test_a_fill_under_a_banner_that_takes_the_text_still_succeeds() -> None:
    """A field under a banner can still be typed in: the look at what covers it only runs once an action failed."""
    async with NotteSession(headless=True) as session:
        _ = await session.window.page.goto(_url(STYLE, FORM.format(inert=""), BANNER))
        result = await session.aexecute(FillAction(selector="#q", value="Lisbon"), raise_on_failure=False)
        assert result.success, result.message
        assert await session.window.page.input_value("#q") == "Lisbon"


@pytest.mark.asyncio
async def test_a_click_refused_as_disabled_names_the_dialog_over_the_control() -> None:
    async with NotteSession(headless=True) as session:
        _ = await session.window.page.goto(_url(STYLE, FORM.format(inert="inert"), WITH_HEADING))
        result = await session.aexecute(ClickAction(selector="#go", timeout=1000), raise_on_failure=False)
        clicked = await session.window.page.evaluate("() => document.body.dataset.clicked")
    assert not result.success
    assert 'Element is disabled: a dialog covers the element: "Legal Terms and Privacy"' in result.message
    assert clicked is None


@pytest.mark.asyncio
async def test_a_click_that_times_out_names_the_element_over_the_control(monkeypatch: pytest.MonkeyPatch) -> None:
    """A click held until its timeout once the element is located (here by a look at its state that never
    returns) says what covered the element."""

    async def never(*args: object, **kwargs: object) -> bool:
        await asyncio.sleep(3600)
        return False

    monkeypatch.setattr(execution_module, "_stays_disabled", never)
    async with NotteSession(headless=True) as session:
        _ = await session.window.page.goto(_url(STYLE, FORM.format(inert=""), BANNER))
        result = await session.aexecute(ClickAction(selector="#go", timeout=500), raise_on_failure=False)
    assert not result.success
    assert result.message == (
        "Action timed out after 500ms: an element covers the element: "
        "<div#cookie-banner> This site uses cookies to improve your experience."
    )


@pytest.mark.asyncio
async def test_a_timeout_waiting_for_an_element_that_never_shows_keeps_its_message() -> None:
    """A Playwright selector locates lazily: the fill times out waiting for its element. Nothing is in the way of an
    element that is not there, and the look does not wait for it either."""
    async with NotteSession(headless=True) as session:
        _ = await session.window.page.goto(_url(STYLE, FORM.format(inert=""), BANNER))
        result = await session.aexecute(FillAction(selector="#missing", value="x", timeout=500), raise_on_failure=False)
    assert not result.success
    assert result.message == "Action timed out after 500ms"


@pytest.mark.asyncio
async def test_a_timeout_before_the_element_is_located_keeps_its_message(monkeypatch: pytest.MonkeyPatch) -> None:
    async def never(*args: object, **kwargs: object) -> None:
        await asyncio.sleep(3600)

    monkeypatch.setattr(execution_module, "_locate", never)
    async with NotteSession(headless=True) as session:
        _ = await session.window.page.goto(_url(STYLE, FORM.format(inert=""), BANNER))
        result = await session.aexecute(ClickAction(selector="#go", timeout=500), raise_on_failure=False)
    assert not result.success
    assert result.message == "Action timed out after 500ms"
