"""`observe()` reads the live state of form controls (value, checked, select options) into `DomNode.state`,
without changing the action ids or the rendered descriptions."""

from collections.abc import AsyncIterator
from urllib.parse import quote

import pytest
import pytest_asyncio
from notte_browser.session import NotteSession
from notte_core.element_state import ElementState, SelectOption, page_fingerprint

PAGE = """
<form>
  <label>Name <input id="name" name="name" value="initial"></label>
  <label>Secret <input id="secret" type="password" name="secret"></label>
  <label>Terms <input id="terms" type="checkbox" name="terms"></label>
  <label>Country
    <select id="country" name="country">
      <option value="fr">France</option>
      <option value="us" selected>United States</option>
      <optgroup label="Closed" disabled><option value="xx">Nowhere</option></optgroup>
    </select>
  </label>
  <textarea id="bio" name="bio"></textarea>
  <div id="rich" contenteditable="true" role="textbox">Rich text</div>
  <button id="menu" type="button" aria-expanded="false">Menu</button>
  <div id="toggle" role="switch" aria-checked="true" tabindex="0">Dark mode</div>
  <button type="submit">Send</button>
</form>
"""


def _data_url(html: str) -> str:
    # observe() returns an empty observation on about:blank, so the page gets a (data:) URL
    return f"data:text/html,{quote(html)}"


@pytest_asyncio.fixture(loop_scope="function")
async def session() -> AsyncIterator[NotteSession]:
    async with NotteSession(headless=True) as session:
        _ = await session.window.page.goto(_data_url(PAGE))
        yield session


def _state_by_selector(session: NotteSession) -> dict[str, ElementState | None]:
    states: dict[str, ElementState | None] = {}
    for node in session.snapshot.interaction_nodes():
        attrs = node.attributes
        if attrs is not None and attrs.id_name is not None:
            states[attrs.id_name] = node.state
    return states


async def _render(session: NotteSession) -> tuple[str, list[tuple[str, str, str | None]]]:
    obs = await session.aobserve()
    return obs.space.description, [(a.id, a.type, a.text_label) for a in obs.space.interaction_actions]


@pytest.mark.asyncio
async def test_observe_reads_the_initial_state(session: NotteSession) -> None:
    _ = await session.aobserve()
    states = _state_by_selector(session)

    assert states["name"] == ElementState(value="initial")
    assert states["secret"] == ElementState(filled=False)
    assert states["terms"] == ElementState(checked=False)
    country = states["country"]
    assert country is not None
    assert country.value == "us"
    assert country.options == (
        SelectOption(value="fr", label="France"),
        SelectOption(value="us", label="United States", selected=True),
        SelectOption(value="xx", label="Nowhere", disabled=True),
    )
    assert [option.label for option in country.selected_options] == ["United States"]
    assert states["bio"] == ElementState(value="")
    assert states["rich"] == ElementState(value="Rich text")
    assert states["menu"] == ElementState(expanded=False)
    assert states["toggle"] == ElementState(checked=True)


@pytest.mark.asyncio
async def test_observe_reads_values_changed_after_load(session: NotteSession) -> None:
    before_description, before_actions = await _render(session)
    before_fingerprint = session.snapshot.fingerprint()

    page = session.window.page
    await page.fill("#name", "typed by the user")
    await page.fill("#secret", "hunter2" * 50)
    await page.check("#terms")
    _ = await page.select_option("#country", "fr")
    await page.fill("#bio", "x" * 500)

    after_description, after_actions = await _render(session)
    states = _state_by_selector(session)

    assert states["name"] == ElementState(value="typed by the user")
    # password values are never read
    assert states["secret"] == ElementState(filled=True)
    assert all("hunter2" not in state.digest() for state in session.snapshot.element_states().values())
    assert states["terms"] == ElementState(checked=True)
    country = states["country"]
    assert country is not None and country.value == "fr"
    assert [option.value for option in country.selected_options] == ["fr"]
    bio = states["bio"]
    assert bio is not None and bio.value == "x" * 200 and bio.value_truncated

    # same ids, types, labels and descriptions: the state is not rendered
    assert after_actions == before_actions
    assert after_description == before_description
    # ...but the fingerprint sees the change
    assert session.snapshot.fingerprint() != before_fingerprint


@pytest.mark.asyncio
async def test_fingerprint_is_stable_when_nothing_changes(session: NotteSession) -> None:
    _ = await session.aobserve()
    first = session.snapshot.fingerprint()
    _ = await session.aobserve()
    assert session.snapshot.fingerprint() == first


@pytest.mark.asyncio
async def test_select_options_are_capped_but_keep_the_selected_one(session: NotteSession) -> None:
    options = "".join(f'<option value="v{i}"{" selected" if i == 70 else ""}>Option {i}</option>' for i in range(80))
    _ = await session.window.page.goto(_data_url(f'<select id="many">{options}</select>'))
    _ = await session.aobserve()
    state = _state_by_selector(session)["many"]

    assert state is not None and state.options is not None
    assert state.options_truncated
    assert len(state.options) == 51
    assert state.options[-1] == SelectOption(value="v70", label="Option 70", selected=True)


def test_page_fingerprint_depends_on_url_ids_labels_and_state() -> None:
    base = page_fingerprint("https://a.test", [("I1", "Name", ElementState(value="a"))])
    assert base == page_fingerprint("https://a.test", [("I1", "Name", ElementState(value="a"))])
    assert base != page_fingerprint("https://b.test", [("I1", "Name", ElementState(value="a"))])
    assert base != page_fingerprint("https://a.test", [("I2", "Name", ElementState(value="a"))])
    assert base != page_fingerprint("https://a.test", [("I1", "Email", ElementState(value="a"))])
    assert base != page_fingerprint("https://a.test", [("I1", "Name", ElementState(value="b"))])
    assert base != page_fingerprint("https://a.test", [("I1", "Name", None)])


@pytest.mark.asyncio
@pytest.mark.parametrize("selector", ["#name", "#bio", "#rich"])
async def test_fingerprint_detects_changes_after_value_cap(session: NotteSession, selector: str) -> None:
    page = session.window.page
    prefix = "x" * 200
    await page.fill(selector, prefix + "first suffix")
    _ = await session.aobserve()
    before = _state_by_selector(session)[selector[1:]]
    fingerprint = session.snapshot.fingerprint()

    await page.fill(selector, prefix + "second suffix")
    _ = await session.aobserve()
    after = _state_by_selector(session)[selector[1:]]
    assert before is not None and after is not None
    assert before.value == after.value == prefix
    assert before.value_truncated and after.value_truncated
    assert before.digest() != after.digest()
    assert session.snapshot.fingerprint() != fingerprint
    # Identical long values still compare equal, without exposing the suffix.
    assert "suffix" not in after.digest()
    stable = session.snapshot.fingerprint()
    _ = await session.aobserve()
    assert session.snapshot.fingerprint() == stable


@pytest.mark.asyncio
async def test_contenteditable_preserves_surrounding_whitespace(session: NotteSession) -> None:
    page = session.window.page
    await page.eval_on_selector("#rich", "el => { el.style.whiteSpace = 'pre-wrap'; }")
    await page.fill("#rich", "hello")
    _ = await session.aobserve()
    fingerprint = session.snapshot.fingerprint()

    await page.eval_on_selector("#rich", "el => { el.textContent = ' hello '; }")
    assert await page.inner_text("#rich") == " hello "
    _ = await session.aobserve()
    assert _state_by_selector(session)["rich"] == ElementState(value=" hello ")
    assert session.snapshot.fingerprint() != fingerprint


@pytest.mark.asyncio
async def test_observe_preserves_mixed_pressed_state(session: NotteSession) -> None:
    page = session.window.page
    await page.eval_on_selector("#menu", "el => el.setAttribute('aria-pressed', 'mixed')")
    _ = await session.aobserve()
    state = _state_by_selector(session)["menu"]
    assert state is not None and state.pressed == "mixed"
    fingerprint = session.snapshot.fingerprint()

    await page.eval_on_selector("#menu", "el => el.removeAttribute('aria-pressed')")
    _ = await session.aobserve()
    state = _state_by_selector(session)["menu"]
    assert state is not None and state.pressed is None
    assert session.snapshot.fingerprint() != fingerprint
