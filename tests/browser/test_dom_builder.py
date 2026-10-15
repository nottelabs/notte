"""`build_dom_tree` on hand-written `buildDomNode.js` payloads (no browser)."""

from typing import Any

from notte_browser.dom.builder import RawFrame, RawNode, build_dom_tree
from notte_core.dom_tree import DomNode
from notte_core.node_type import NodeRole, NodeType

BBOX = {
    "x": 1,
    "y": 2,
    "width": 3,
    "height": 4,
    "scroll_x": 0,
    "scroll_y": 0,
    "viewport_width": 10,
    "viewport_height": 10,
}


def _element(tag: str, xpath: str, children: list[str], highlight: int | None = None, **attributes: str) -> RawNode:
    node: dict[str, Any] = dict(tagName=tag, xpath=xpath, attributes=attributes, children=children, isVisible=True)
    if highlight is not None:
        node.update(isInteractive=True, highlightIndex=highlight, bbox=dict(BBOX))
    return node  # pyright: ignore[reportReturnType]


def _text(text: str, visible: bool = True) -> RawNode:
    return {"type": "TEXT_NODE", "text": text, "isVisible": visible}


def _frame(nodes: dict[str, RawNode], root_id: str) -> RawFrame:
    return RawFrame(root_id=root_id, nodes=nodes)


def _by_text(root: DomNode) -> dict[str, DomNode]:
    return {node.text: node for node in root.flatten() if node.type is not NodeType.TEXT}


def test_ids_follow_the_document_order_per_short_id() -> None:
    nodes: dict[str, RawNode] = {
        "1": _text("Home"),
        "2": _element("a", "/body/a", ["1"], highlight=0),
        "3": _element("input", "/body/input[1]", [], highlight=1, type="checkbox", name="agree"),
        "4": _element("input", "/body/input[2]", [], highlight=2, placeholder="Email"),
        "5": _element("div", "/body/div[1]", [], highlight=3, role="doc-chapter", title="chapter"),
        "6": _element("div", "/body/div[2]", [], highlight=4, title="clickable"),
        "7": _element("button", "/body/button", [], title="not highlighted"),
        "8": _element("body", "/body", ["2", "3", "4", "5", "6", "7"]),
    }
    root = build_dom_tree(_frame(nodes, "8"), url="https://example.com")
    assert root is not None and root.role is NodeRole.WEBAREA
    nodes_by_text = _by_text(root)
    assert nodes_by_text["Home"].id == "L1"
    # a checkbox gets a button id: `B` is matched first in `NodeRole.short_id`
    assert nodes_by_text["agree"].id == "B1"
    assert nodes_by_text["Email"].id == "I1"
    # a highlighted node whose role is not a `NodeRole` gets no id
    assert nodes_by_text["chapter"].role == "doc-chapter" and nodes_by_text["chapter"].id is None
    assert nodes_by_text["clickable"].id == "M1"
    assert nodes_by_text["not highlighted"].id is None
    assert [node.id for node in root.interaction_nodes()] == ["L1", "B1", "I1", "M1"]
    assert all(child.parent is root for child in root.children)


def test_grafted_frames_are_numbered_in_place() -> None:
    child_nodes: dict[str, RawNode] = {
        "1": _text("Inside"),
        "2": _element("button", "/body/button", ["1"], highlight=1),
        "3": _element("body", "/body", ["2"]),
    }
    nodes: dict[str, RawNode] = {
        "1": _text("Before"),
        "2": _element("button", "/body/button[1]", ["1"], highlight=0),
        "3": _element("iframe", "/body/iframe", [], id="frame"),
        "4": _text("After"),
        "5": _element("button", "/body/button[2]", ["4"], highlight=2),
        "6": _element("body", "/body", ["2", "3", "5"]),
    }
    nodes["3"]["frame"] = _frame(child_nodes, "3")
    root = build_dom_tree(_frame(nodes, "6"), url="https://example.com")
    assert root is not None
    assert [(node.id, node.text) for node in root.interaction_nodes()] == [
        ("B1", "Before"),
        ("B2", "Inside"),
        ("B3", "After"),
    ]
    inside = _by_text(root)["Inside"].computed_attributes.selectors
    iframe = _by_text(root)[""].computed_attributes.selectors
    assert inside is not None and iframe is not None
    assert inside.in_iframe and not iframe.in_iframe
    assert inside.iframe_parent_css_selectors == [iframe.css_selector]
    assert inside.notte_selector is not None and inside.notte_selector.startswith("https://example.com:")


def test_names_and_attributes() -> None:
    nodes: dict[str, RawNode] = {
        "1": _text("  Visible "),
        "2": _text("hidden", visible=False),
        "3": _element("span", "/body/a/span", ["2"]),
        "4": _element("a", "/body/a", ["1", "3"], highlight=0, href="/x"),
        "5": _element("a", "/body/a[2]", [], highlight=1, href="/y"),
        "6": _element("wiz_menu_item", "/body/wiz_menu_item", [], **{"x-aria-label": "Menu"}),
        "7": _element("button", "/body/button", [], highlight=2, type="submit"),
        "8": _element("body", "/body", ["4", "5", "6", "7"]),
    }
    root = build_dom_tree(_frame(nodes, "8"), url="https://example.com")
    assert root is not None
    link, empty_link, menu, button = root.children
    assert link.text == "Visible"
    # an empty link is named after its href
    assert empty_link.text == "/y"
    # `wiz_` tags are renamed and `*aria-*` attributes normalised
    assert menu.attributes is not None and menu.attributes.tag_name == "menu-item"
    assert menu.attributes.aria_label == "Menu" and menu.text == "Menu" and menu.role is NodeRole.MENUITEM
    # a button without text is named after its type
    assert button.text == "submit"
    assert root.text == "body content"
