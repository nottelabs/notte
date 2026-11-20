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
# a field that keeps nothing, with nothing in its way
REFUSING = """<input id="q" oninput="this.value = ''">"""


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


@pytest.mark.asyncio
async def test_a_fill_behind_a_native_modal_dialog_names_it() -> None:
    async with NotteSession(headless=True) as session:
        message = await _fill(session, _url(FORM.format(inert=""), NATIVE))
    assert 'a dialog covers the element: "Allow optional cookies?"' in message


@pytest.mark.asyncio
async def test_a_fill_in_an_inert_part_with_no_dialog_shown_says_so() -> None:
    async with NotteSession(headless=True) as session:
        message = await _fill(session, _url(FORM.format(inert="inert")))
    assert "The field stayed empty after typing: the element is inert" in message


@pytest.mark.asyncio
async def test_a_fill_that_a_field_refuses_keeps_its_message() -> None:
    async with NotteSession(headless=True) as session:
        message = await _fill(session, _url(REFUSING))
    assert message.endswith("The field stayed empty after typing")


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
