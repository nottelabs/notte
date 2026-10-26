"""`observe()` reads the live state of form controls (value, checked, select options) into `DomNode.state`,
without changing the action ids or the rendered descriptions."""

from collections.abc import AsyncIterator
from typing import Literal
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


@pytest.mark.asyncio
async def test_observation_carries_the_live_state_and_fingerprint(session: NotteSession) -> None:
    await session.window.page.fill("#name", "typed")
    obs = await session.aobserve()
    # what a cloud observe response serializes, so that remote act() sees the same state as local
    assert obs.element_states == session.snapshot.element_states()
    assert obs.fingerprint == session.snapshot.fingerprint()
    assert any(state.value == "typed" for state in (obs.element_states or {}).values())


VAULT_URL = "http://vault.test/"
VAULT_PAGE = """<html><body><form>
<input id="email" type="email" name="email">
<input id="user" name="username">
<input id="card" name="cardnumber" autocomplete="cc-number">
<input id="pw" type="password" name="password">
</form></body></html>"""
SECRETS = {
    "email": "real-user@example.com",
    "username": "real-user-42",
    "password": "s3cr3t-pw",  # pragma: allowlist secret
}
CARD = {
    "card_holder_name": "Ada Lovelace",
    "card_number": "5555 4444 3333 1111",
    "card_cvv": "737",
    "card_full_expiration": "03/30",
}


async def _vault_session(session: NotteSession, secrets: dict[str, str], card_number: str) -> None:
    """The vault types an email, a username, a card number and a password into the page."""
    from notte_core.actions import FillAction
    from notte_core.credentials import CARD_NUMBER, EMAIL, PASSWORD, USERNAME

    from tests.mock.mock_vault import MockVault

    page = session.window.page
    _ = await page.route(VAULT_URL, lambda route: route.fulfill(body=VAULT_PAGE, content_type="text/html"))
    _ = await page.goto(VAULT_URL)
    vault = MockVault({VAULT_URL: secrets})  # pyright: ignore[reportArgumentType]
    await vault.set_credit_card_async(**{**CARD, "card_number": card_number})  # pyright: ignore[reportArgumentType]
    session.vault = vault
    _ = await session.aobserve()
    for selector, placeholder in (("#email", EMAIL), ("#user", USERNAME), ("#card", CARD_NUMBER), ("#pw", PASSWORD)):
        result = await session.aexecute(FillAction(selector=selector, value=placeholder), raise_on_failure=True)
        assert result.success


@pytest.mark.asyncio
async def test_observation_carries_only_placeholders_for_values_the_vault_typed(session: NotteSession) -> None:
    from notte_core.credentials import CARD_NUMBER, EMAIL, USERNAME

    await _vault_session(session, SECRETS, CARD["card_number"])
    page = session.window.page
    # the page holds the real values...
    assert await page.input_value("#email") == SECRETS["email"]
    assert await page.input_value("#card") == CARD["card_number"]

    obs = await session.aobserve()
    payload = obs.model_dump_json()
    # ...the observation (and what it serializes) only their placeholders
    for value in (*SECRETS.values(), CARD["card_number"]):
        assert value not in payload
    values = {state.value for state in (obs.element_states or {}).values()}
    assert {EMAIL, USERNAME, CARD_NUMBER} <= values
    # a password field never carries its value: only whether it is filled
    password = [s for s in (obs.element_states or {}).values() if s.filled is not None]
    assert len(password) == 1 and password[0].filled is True and password[0].value is None
    assert obs.fingerprint == session.snapshot.fingerprint(obs.element_states)
    assert obs.fingerprint != session.snapshot.fingerprint()


@pytest.mark.asyncio
async def test_fingerprint_does_not_depend_on_the_secret(session: NotteSession) -> None:
    await _vault_session(session, SECRETS, CARD["card_number"])
    first = (await session.aobserve()).fingerprint
    # other secrets typed into the same fields: same placeholders, same fingerprint
    other = {
        "email": "someone-else@example.com",
        "username": "someone-else",
        "password": "another-pw",  # pragma: allowlist secret
    }
    await _vault_session(session, other, "4000 0566 5566 5556")
    assert (await session.aobserve()).fingerprint == first


def test_observation_requires_the_secrets_to_mask() -> None:
    import inspect

    from notte_core.observation import Observation

    parameter = inspect.signature(Observation.from_snapshot).parameters["secrets"]
    # no default: a caller cannot build an observation from a snapshot without saying what to mask
    assert parameter.default is inspect.Parameter.empty and parameter.kind is inspect.Parameter.KEYWORD_ONLY


def test_element_state_masking() -> None:
    state = ElementState(
        value="code 123456",
        options=(SelectOption(value="123456", label="Use 123456", selected=True), SelectOption(value="x", label="x")),
    )
    masked = state.masked({"123456": "999779", "": "ignored"})
    assert masked.value == "code 999779"
    # option values identify the option to select: they stay exact
    assert masked.options == state.options
    assert state.masked({}) is state


def test_masking_a_cut_value() -> None:
    secrets = {"737": "[CardCVVPlaceholder]", "a" * 250: "user@example.org"}
    # a secret past the cut: not visible, but the digest of the whole value is dropped
    past = ElementState(value="x" * 200, value_truncated=True, value_digest="0123456789abcdef")
    assert past.masked(secrets) == ElementState(value="x" * 200, value_truncated=True)
    # a secret across the cut: its visible start is masked (from 3 characters: shorter starts match ordinary text)
    across = ElementState(value="x" * 197 + "737", value_truncated=True, value_digest="d")
    assert across.masked({"7375": "[CardCVVPlaceholder]"}).value == "x" * 197 + "[CardCVVPlaceholder]"
    # a secret longer than the cut
    long = ElementState(value="a" * 200, value_truncated=True, value_digest="d")
    assert long.masked(secrets).value == "user@example.org" and long.masked(secrets).value_digest is None
    # no secrets: unchanged, digest kept
    assert past.masked({}) is past


SORTED_TABLE = """
<table>
  <thead><tr>
    <th id="age" aria-sort="descending" tabindex="0">Age <button id="age-sort">Sort by age</button></th>
    <th id="name" tabindex="0">Name <button id="name-sort">Sort by name</button></th>
  </tr></thead>
  <tbody><tr><td>36</td><td>Ada</td></tr></tbody>
</table>
<div role="grid"><div role="row">
  <div role="columnheader" aria-sort="ascending"><button id="city-sort">City</button></div>
</div></div>
"""


@pytest.mark.asyncio
async def test_the_sort_order_of_a_column_is_read_on_its_header_and_sort_button() -> None:
    async with NotteSession(headless=True) as session:
        _ = await session.window.page.goto(_data_url(SORTED_TABLE))
        _ = await session.aobserve()
        states = _state_by_selector(session)

    assert states["age-sort"] == ElementState(sort="descending")
    assert states["city-sort"] == ElementState(sort="ascending")
    # an unsorted column has no sort order
    assert states["name-sort"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("header", ["th", 'div role="columnheader"'])
@pytest.mark.parametrize("sort", ["ascending", "descending", "other", "none"])
async def test_the_sort_order_is_read_on_a_directly_clickable_header(
    header: str, sort: Literal["ascending", "descending", "other", "none"]
) -> None:
    tag = header.split()[0]
    html = f'<{header} id="sort" aria-sort="{sort}" onclick="void(0)">Age</{tag}>'
    if tag == "th":
        html = f"<table><thead><tr>{html}</tr></thead></table>"
    else:
        html = f'<div role="grid"><div role="row">{html}</div></div>'

    async with NotteSession(headless=True) as session:
        _ = await session.window.page.goto(_data_url(html))
        _ = await session.aobserve()
        states = _state_by_selector(session)

    assert states["sort"] == (None if sort == "none" else ElementState(sort=sort))
