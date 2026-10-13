"""Pin action fields that observe's text goldens do not serialize."""

import pytest
from notte_browser.dom.builder import build_dom_tree
from notte_browser.tagging.action_space import build_action_space
from notte_core.actions import ClickAction, FillAction, SelectDropdownOptionAction
from notte_core.browser.dom_tree import DomNode
from notte_core.browser.node_type import NodeType

from .test_dom_builder import _element, _frame, _text


@pytest.mark.parametrize(
    ("tag", "attributes", "prefix", "action_type", "label", "description"),
    [
        ("button", {}, "B", "click", "Visible", "<button></button>"),
        ("a", {"href": "/home"}, "L", "click", "Visible", '<a href="/home"></a>'),
        ("input", {"placeholder": "Email"}, "I", "fill", "Email", '<input placeholder="Email"></input>'),
        ("textarea", {"placeholder": "Message"}, "I", "fill", "", '<textarea placeholder="Message"></textarea>'),
        ("select", {}, "I", "select_dropdown_option", "Visible", "<select></select>"),
        ("option", {}, "O", "select_dropdown_option", "Visible", "<option></option>"),
        (
            "input",
            {"type": "checkbox", "name": "agree"},
            "B",
            "click",
            "agree",
            '<input type="checkbox" name="agree"></input>',
        ),
        (
            "input",
            {"type": "radio", "name": "choice"},
            "B",
            "click",
            "choice",
            '<input type="radio" name="choice"></input>',
        ),
        ("img", {"alt": "Picture"}, "F", "click", "Visible", '<img alt="Picture"></img>'),
        ("div", {}, "M", "click", "Visible", "<div></div>"),
    ],
)
def test_complete_action_fields(
    tag: str, attributes: dict[str, str], prefix: str, action_type: str, label: str, description: str
) -> None:
    root = build_dom_tree(
        _frame({"0": _element(tag, f"/body/{tag}", ["1"], highlight=0, **attributes), "1": _text("Visible")}, "0"),
        url="https://example.com:8443/form",
    )
    assert root is not None
    action = build_action_space(root).interaction_actions[0]
    action_id = f"{prefix}1"
    expected = (
        FillAction(id=action_id, value="<sample_value>", press_enter=False)
        if action_type == "fill"
        else SelectDropdownOptionAction(
            id=action_id,
            value=action_id if prefix == "O" else "<sample_value>",
            press_enter=None if prefix == "O" else False,
        )
        if action_type == "select_dropdown_option"
        else ClickAction(id=action_id)
    )
    expected.selector = root.computed_attributes.selectors
    expected.category = "Interaction action"
    expected.text_label = label
    expected.description = description
    assert action.model_dump() == expected.model_dump()
    # Per-action descriptions historically render a childless node; the page description includes text.
    assert action.description == description
    assert (action.param.model_dump() if action.param is not None else None) == (
        {"name": "value", "type": "string", "default": None, "values": []} if prefix == "I" else None
    )


def dialog_tree() -> DomNode:
    root = build_dom_tree(
        _frame(
            {
                "0": _element("body", "/body", ["1", "3"]),
                "1": _element("button", "/body/button", ["2"], highlight=0, title="x" * 80),
                "2": _text("Outside"),
                "3": _element("dialog", "/body/dialog", ["4"]),
                "4": _element("button", "/body/dialog/button", ["5", "6"], highlight=1),
                "5": _text("Outer"),
                "6": _element("a", "/body/dialog/button/a", ["7"], highlight=2),
                "7": _text("Inner"),
            },
            "0",
        ),
        url="https://example.com",
    )
    assert root is not None
    return root


def test_dialogs_nested_actions_and_attribute_truncation() -> None:
    root = dialog_tree()
    space = build_action_space(root)
    assert "Outside" not in space.description
    assert "B2[:]<button>Outer</button>" in space.description
    assert "L1[:]<a>Inner</a>" in space.description
    assert [(a.id, a.text_label, a.description) for a in space.interaction_actions] == [
        ("B1", "Outside", f'<button title="{"x" * 80}"></button>'),
        ("B2", "Outer Inner", "<button></button>"),
        ("L1", "Inner", "<a></a>"),
    ]
    outside = root.children[0]
    assert outside.type is NodeType.INTERACTION
    assert f'title="{"x" * 60}..."' in build_action_space(outside).description


def test_canonical_nodes_keep_names_children_and_selector_identity() -> None:
    root = dialog_tree()
    outside, dialog = root.children
    outer = dialog.children[0]
    inner = outer.children[1]
    assert root.find("B2") is outer
    assert root.interaction_nodes()[1] is outer
    assert outer.children[1] is inner and inner.parent is outer
    # Accessible names stay on the canonical nodes; action labels are explicitly inner_text().
    assert outside.text == "x" * 80 and outside.inner_text() == "Outside"
    selectors = outside.computed_attributes.selectors
    assert selectors is not None
    assert selectors is root.interaction_nodes()[0].computed_attributes.selectors
    assert root.find("B1") is outside and outside.get_url() == "https://example.com"
    assert build_action_space(root).interaction_actions[0].selectors is selectors


def test_highlighted_text_role_keeps_its_action_description() -> None:
    root = build_dom_tree(
        _frame({"0": _element("div", "/body/div", ["1"], highlight=0, role="text"), "1": _text(" Visible ")}, "0"),
        url="https://example.com",
    )
    assert root is not None
    action = build_action_space(root).interaction_actions[0]
    assert (action.id, action.text_label, action.description) == ("M1", " Visible ", '<div role="text">Visible</div>')
