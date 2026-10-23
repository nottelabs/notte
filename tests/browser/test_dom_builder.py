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
    return {"type": "TEXT_NODE", "text": text, "isInViewport": visible}


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


def _ids(root: DomNode) -> list[tuple[str, str]]:
    return [(node.id or "", node.inner_text()) for node in root.interaction_nodes()]


def test_generic_clickables_inside_a_control_get_no_id() -> None:
    # GitHub's "Fork" link: the pointer cursor of the link is inherited by its label and counter
    nodes: dict[str, RawNode] = {
        "1": _text("Fork"),
        "2": _element("span", "/body/a/span/span[1]", ["1"], highlight=1),
        "3": _text("17.1k"),
        "4": _element("span", "/body/a/span/span[2]", ["3"], highlight=2),
        "5": _element("span", "/body/a/span", ["2", "4"], highlight=3),
        "6": _element("a", "/body/a", ["5"], highlight=0, href="/fork"),
        # an element inside a control with a name of its own may do something else
        "7": _text("Tag"),
        "8": _element("span", "/body/button/span", [], highlight=5, **{"aria-label": "Remove tag"}),
        "9": _element("button", "/body/button", ["7", "8"], highlight=4),
        "10": _element("body", "/body", ["6", "9"]),
    }
    nodes["8"]["accessibleName"] = "Remove tag"
    root = build_dom_tree(_frame(nodes, "10"), url="https://example.com")
    assert root is not None
    assert _ids(root) == [("L1", "Fork 17.1k"), ("B1", "Tag"), ("M1", "")]
    # the link is rendered with its text, which its highlighted children used to hide
    fork = root.children[0]
    assert fork.type is NodeType.INTERACTION
    inner = [node for node in fork.flatten()[1:] if node.type is not NodeType.TEXT]
    assert len(inner) == 3 and all(node.id is None and node.type is NodeType.OTHER for node in inner)


def test_a_generic_clickable_around_one_control_with_the_same_name_gets_no_id() -> None:
    nodes: dict[str, RawNode] = {
        # Amazon's search button: `<div>Go</div>` with a pointer cursor around the submit input
        "1": _text("Go"),
        "2": _element("span", "/body/div[1]/span", ["1"]),
        "3": _element("input", "/body/div[1]/input", [], highlight=1, type="submit"),
        "4": _element("div", "/body/div[1]", ["2", "3"], highlight=0),
        # a clickable row around a button with another name: both are kept
        "5": _text("10:40 AM Paris - Tokyo"),
        "6": _element("button", "/body/div[2]/button", [], highlight=3, **{"aria-label": "Emissions"}),
        "7": _element("div", "/body/div[2]", ["5", "6"], highlight=2),
        # a clickable element on its own is kept
        "8": _text("Widgets"),
        "9": _element("span", "/body/span", ["8"], highlight=4),
        "10": _element("body", "/body", ["4", "7", "9"]),
    }
    nodes["3"]["accessibleName"] = "Go"
    nodes["6"]["accessibleName"] = "Emissions"
    root = build_dom_tree(_frame(nodes, "10"), url="https://example.com")
    assert root is not None
    assert _ids(root) == [("B1", ""), ("M1", "10:40 AM Paris - Tokyo"), ("B2", ""), ("M2", "Widgets")]


def test_generic_clickables_that_may_do_something_else_keep_their_id() -> None:
    nodes: dict[str, RawNode] = {
        # inside a control, with a click handler of its own: `<button>Tag<span onclick="...">×</span></button>`
        "1": _text("Tag"),
        "2": _text("×"),
        "3": _element("span", "/body/button/span", ["2"], highlight=1, onclick="removeTag()"),
        "4": _element("button", "/body/button", ["1", "3"], highlight=0),
        # a row named "Open details" around an icon button named "Favorite"
        "5": _element("button", "/body/div[1]/button", [], highlight=3),
        "6": _element("div", "/body/div[1]", ["5"], highlight=2, **{"aria-label": "Open details"}),
        # two wrappers around a "Go" button: both are duplicates
        "7": _element("input", "/body/div[2]/div/input", [], highlight=6, type="submit"),
        "8": _element("div", "/body/div[2]/div", ["7"], highlight=5),
        "9": _element("div", "/body/div[2]", ["8"], highlight=4),
        "10": _element("body", "/body", ["4", "6", "9"]),
    }
    nodes["3"]["clickHandler"] = True
    nodes["5"]["accessibleName"] = "Favorite"
    nodes["6"]["accessibleName"] = "Open details"
    nodes["7"]["accessibleName"] = "Go"
    root = build_dom_tree(_frame(nodes, "10"), url="https://example.com")
    assert root is not None
    ids = [(node.id, node.accessible_name) for node in root.interaction_nodes()]
    assert ids == [("B1", None), ("M1", None), ("M2", "Open details"), ("B2", "Favorite"), ("B3", "Go")]
