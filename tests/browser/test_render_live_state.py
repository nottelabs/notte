"""The page description says what each control with an id holds: `checked`, `mixed`, `pressed`, `selected` and
`expanded` flags like `disabled`, and its current value (`value="..."`, a `<select>`'s selected option). Agents that
read only this text can tell that a goal already holds. Password values and vault secrets never appear in it."""

from collections.abc import Sequence
from typing import Any
from urllib.parse import quote

import pytest
from notte_browser.action_space import build_action_space, format_node, render_node
from notte_browser.dom.builder import RawNode, build_dom_tree
from notte_browser.session import NotteSession
from notte_core.act.space import without_live_state
from notte_core.dom_tree import DomNode
from notte_core.element_state import ElementState

from .test_dom_builder import _element, _frame, _text


def _control(tag: str, state: dict[str, Any] | None, children: Sequence[RawNode] = (), **attributes: str) -> DomNode:
    """A page with one interactive `tag` holding `state` (the DOM script's `state` payload)."""
    node = _element(tag, f"/body/{tag}", [str(i + 1) for i in range(len(children))], highlight=0, **attributes)
    if state is not None:
        node["state"] = state  # pyright: ignore[reportGeneralTypeIssues]
    nodes: dict[str, RawNode] = {"0": node, **{str(i + 1): child for i, child in enumerate(children)}}
    root = build_dom_tree(_frame(nodes, "0"), url="https://example.com")
    assert root is not None
    return root


def _line(root: DomNode, secrets: dict[str, str] | None = None) -> str:
    lines = format_node(root, [], max_len_per_attribute=60, secrets={} if secrets is None else secrets)
    assert len(lines) == 1, lines
    return lines[0]


@pytest.mark.parametrize(
    ("tag", "attributes", "state", "children", "expected"),
    [
        ("input", {"type": "checkbox"}, {"checked": True}, [], 'B1[:]<input type="checkbox" checked></input>'),
        (
            "input",
            {"type": "radio", "name": "c"},
            {"checked": True},
            [],
            'B1[:]<input type="radio" name="c" checked></input>',
        ),
        ("div", {"role": "checkbox"}, {"mixed": True}, [_text("All")], '<div role="checkbox" mixed>All</div>'),
        ("button", {}, {"pressed": True}, [_text("Bold")], "B1[:]<button pressed>Bold</button>"),
        (
            "button",
            {"role": "tab"},
            {"selected": True},
            [_text("Details")],
            '<button role="tab" selected>Details</button>',
        ),
        ("button", {}, {"expanded": True}, [_text("Menu")], "B1[:]<button expanded>Menu</button>"),
        # `aria-expanded` already says it
        (
            "button",
            {"aria_expanded": "true"},
            {"expanded": True},
            [_text("Menu")],
            '<button aria_expanded="true">Menu</button>',
        ),
        (
            "input",
            {"type": "text", "name": "email"},
            {"value": "a@b.co"},
            [],
            'I1[:]<input type="text" name="email" value="a@b.co"></input>',
        ),
        # the live value replaces the one the page was served with
        (
            "input",
            {"name": "q", "value": "served"},
            {"value": "typed"},
            [],
            'I1[:]<input name="q" value="typed"></input>',
        ),
        ("textarea", {"name": "bio"}, {"value": "Hello"}, [], 'I1[:]<textarea name="bio" value="Hello"></textarea>'),
        # a textarea's text is its served value: cleared by the user, it holds nothing
        ("textarea", {"name": "bio"}, {"value": ""}, [_text("served")], 'I1[:]<textarea name="bio"></textarea>'),
        (
            "select",
            {"name": "country"},
            {
                "value": "it",
                "options": [{"value": "fr", "label": "France"}, {"value": "it", "label": "Italy", "selected": True}],
            },
            [_text("France Italy")],
            'I1[:]<select name="country" value="Italy">France Italy</select>',
        ),
        (
            "input",
            {"type": "password", "name": "pw"},
            {"filled": True},
            [],
            'I1[:]<input type="password" name="pw"></input>',
        ),
        # nor the value a password field was served with
        (
            "input",
            {"type": "password", "value": "served-pw"},
            {"filled": True},
            [],
            'I1[:]<input type="password"></input>',
        ),
        ("input", {"type": "checkbox"}, {"checked": False}, [], 'B1[:]<input type="checkbox"></input>'),
        ("input", {"type": "text"}, {"value": ""}, [], 'I1[:]<input type="text"></input>'),
        ("input", {"placeholder": "Email"}, None, [], 'I1[:]<input placeholder="Email"></input>'),
        # a submit button's value is its label, not a live value
        (
            "input",
            {"type": "submit", "value": "Send"},
            {"value": "Send"},
            [],
            'B1[:]<input type="submit" value="Send"></input>',
        ),
    ],
)
def test_a_control_with_an_id_says_what_it_holds(
    tag: str, attributes: dict[str, str], state: dict[str, Any] | None, children: list[RawNode], expected: str
) -> None:
    line = _line(_control(tag, state, children, **attributes))
    if expected.startswith("<"):
        # the id depends on the role (an ARIA checkbox or a tab is an `M` or `B` element)
        line = line.split("[:]", 1)[1]
    assert line == expected


def test_a_value_is_cut_like_the_other_attributes_and_escaped() -> None:
    long = _control("input", {"value": "y" * 80}, type="text")
    assert _line(long) == f'I1[:]<input type="text" value="{"y" * 60}..."></input>'
    # cut by the browser (at 200 characters), it says so without a length cap too
    cut = _control("textarea", {"value": "z" * 200, "valueTruncated": True})
    assert render_node(cut, secrets={}) == f'<textarea value="{"z" * 200}..."></textarea>'
    quoted = _control("textarea", {"value": 'say "hi" <b> &\nbye'})
    assert _line(quoted) == 'I1[:]<textarea value="say &quot;hi&quot; &lt;b&gt; &amp;&#10;bye"></textarea>'


def test_the_action_descriptions_and_a_render_without_secrets_carry_no_live_state() -> None:
    root = _control("input", {"value": "a@b.co"}, type="email")
    space = build_action_space(root)
    assert space.description.endswith('I1[:]<input type="email"></input>')
    with_state = build_action_space(root, secrets={})
    assert with_state.description.endswith('I1[:]<input type="email" value="a@b.co"></input>')
    # the per-action description is the element's markup, the same whatever it holds
    assert [action.description for action in with_state.interaction_actions] == ['<input type="email"></input>']


def test_a_secret_the_vault_typed_is_rendered_as_its_placeholder() -> None:
    secrets = {"real-user@example.com": "{{email}}", "s3cr3t-pw": "{{password}}"}  # pragma: allowlist secret
    field = _control("input", {"value": "real-user@example.com"}, type="email")
    assert _line(field, secrets) == 'I1[:]<input type="email" value="{{email}}"></input>'
    # also when the browser cut the value partway through the secret
    cut = _control("input", {"value": "note: s3cr", "valueTruncated": True, "valueDigest": "abc"}, type="text")
    line = _line(cut, secrets)
    assert "s3cr" not in line and line == 'I1[:]<input type="text" value="note: {{password}}..."></input>'


def test_act_shows_the_live_state_once() -> None:
    """Act's html labels and page text leave the rendered state out: its elements carry it from `page.states`."""
    assert (
        without_live_state('I1[:]<input type="text" name="email" value="a@b.co"></input>', ElementState(value="a@b.co"))
        == 'I1[:]<input type="text" name="email"></input>'
    )
    assert (
        without_live_state('<input type="checkbox" title="checked" checked></input>', ElementState(checked=True))
        == '<input type="checkbox" title="checked"></input>'
    )
    assert (
        without_live_state('  I2[:]<select name="c" value="Italy">France', ElementState(value="it", options=()))
        == '  I2[:]<select name="c">France'
    )
    # a submit button's value is its label, kept
    submit = '<input type="submit" value="Send"></input>'
    assert without_live_state(submit, ElementState(value="Send")) == submit
    # without live state (an observation that carries none), the line is the page's own
    served = '<input type="text" value="served"></input>'
    assert without_live_state(served, None) == served


PRIVATE_PAGE = """
<label>Password <input id="pw" type="password" name="password"></label>
<label>Email <input id="email" type="email" name="email"></label>
<label>Remember me <input id="remember" type="checkbox"></label>
"""


@pytest.mark.asyncio
async def test_a_typed_password_or_vault_credential_never_appears_in_the_description() -> None:
    from notte_core.actions import FillAction
    from notte_core.credentials import EMAIL, PASSWORD

    from tests.mock.mock_vault import MockVault

    url = "http://private.test/"
    credentials = {"email": "real-user@example.com", "password": "s3cr3t-pw"}  # pragma: allowlist secret
    async with NotteSession(headless=True) as session:
        page = session.window.page
        _ = await page.route(url, lambda route: route.fulfill(body=PRIVATE_PAGE, content_type="text/html"))
        _ = await page.goto(url)
        session.vault = MockVault({url: credentials})  # pyright: ignore[reportArgumentType]
        _ = await session.aobserve()
        for selector, placeholder in (("#email", EMAIL), ("#pw", PASSWORD)):
            result = await session.aexecute(FillAction(selector=selector, value=placeholder), raise_on_failure=True)
            assert result.success
        await page.check("#remember")
        assert await page.input_value("#pw") == credentials["password"]

        obs = await session.aobserve()
        description = obs.space.description
        assert credentials["password"] not in description and credentials["email"] not in description
        assert f'<input type="email" name="email" value="{EMAIL}"></input>' in description
        assert '<input type="password" name="password"></input>' in description
        assert '<input type="checkbox" checked></input>' in description

        # a password the user typed (not the vault) is never read, so never rendered either
        session.vault = None
        await page.fill("#pw", "typed-by-hand")
        obs = await session.aobserve()
        assert "typed-by-hand" not in obs.model_dump_json()
        assert '<input type="password" name="password"></input>' in obs.space.description


@pytest.mark.asyncio
async def test_observe_shows_a_checked_box_a_filled_field_and_a_chosen_option() -> None:
    html = """
    <label>Checkbox 1 <input type="checkbox"></label>
    <label>Checkbox 2 <input type="checkbox" checked></label>
    <label>Email <input id="email" type="text" name="email"></label>
    <select name="country"><option>France</option><option>Italy</option></select>
    """
    async with NotteSession(headless=True) as session:
        _ = await session.window.page.goto(f"data:text/html,{quote(html)}")
        await session.window.page.fill("#email", "a@b.co")
        _ = await session.window.page.select_option("select", "Italy")
        lines = (await session.aobserve()).space.description.splitlines()[1:]
        assert lines == [
            "_[:]Checkbox 1",
            'B1[:]<input type="checkbox"></input>',
            "_[:]Checkbox 2",
            'B2[:]<input type="checkbox" checked></input>',
            "_[:]Email",
            'I1[:]<input type="text" name="email" value="a@b.co"></input>',
            'I2[:]<select name="country" value="Italy">France',
            "Italy</select>",
        ]
