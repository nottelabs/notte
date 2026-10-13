import pytest
from notte_core.browser.dom_tree import ComputedDomAttributes, DomAttributes, DomNode, NodeSelectors
from notte_core.browser.node_type import NodeRole, NodeType


def test_node_role_from_value():
    # Test valid role conversion
    assert NodeRole.from_value("BUTTON") == NodeRole.BUTTON
    assert NodeRole.from_value("TEXT") == NodeRole.TEXT

    # Test invalid role returns string
    assert NodeRole.from_value("invalid_role") == "invalid_role"


@pytest.mark.parametrize("role", list(NodeRole))
def test_node_role_interactivity(role: NodeRole) -> None:
    interactive = {
        "button",
        "link",
        "combobox",
        "textbox",
        "checkbox",
        "searchbox",
        "radio",
        "tab",
        "listbox",
        "menuitem",
        "menuitemcheckbox",
        "menuitemradio",
        "slider",
        "switch",
        "option",
    }
    assert role.is_interactive() is (role.value in interactive)


def test_notte_node():
    # Create a simple node hierarchy
    child_node = DomNode(
        id="child1",
        role=NodeRole.BUTTON,
        text="Click me",
        type=NodeType.INTERACTION,
        children=[],
        attributes=None,
        computed_attributes=ComputedDomAttributes(),
    )

    parent_node = DomNode(
        id="parent1",
        role=NodeRole.GROUP,
        text="Parent Group",
        type=NodeType.OTHER,
        children=[child_node],
        attributes=None,
        computed_attributes=ComputedDomAttributes(),
    )

    # Test find method
    assert parent_node.find("child1") is child_node
    assert parent_node.interaction_nodes()[0] is child_node
    assert parent_node.find("nonexistent") is None

    # Test is_interaction method
    assert child_node.is_interaction() is True
    assert parent_node.is_interaction() is False

    # Test get_role_str method
    assert child_node.get_role_str() == "button"
    assert parent_node.get_role_str() == "group"

    # Test string role
    string_role_node = DomNode(
        id="str1",
        role="custom_role",
        text="Custom",
        type=NodeType.OTHER,
        children=[],
        attributes=None,
        computed_attributes=ComputedDomAttributes(),
    )
    assert string_role_node.get_role_str() == "custom_role"
    assert string_role_node.is_interaction() is False


def test_notte_node_flatten():
    # Create a nested structure

    button1 = DomNode(
        id="btn1",
        role=NodeRole.BUTTON,
        text="Button 1",
        type=NodeType.INTERACTION,
        children=[],
        attributes=None,
        computed_attributes=ComputedDomAttributes(),
    )

    button2 = DomNode(
        id="btn2",
        role=NodeRole.BUTTON,
        text="Button 2",
        type=NodeType.INTERACTION,
        children=[],
        attributes=None,
        computed_attributes=ComputedDomAttributes(),
    )

    text_node = DomNode(
        id="txt1",
        role=NodeRole.TEXT,
        text="Some text",
        type=NodeType.TEXT,
        children=[],
        attributes=None,
        computed_attributes=ComputedDomAttributes(),
    )

    group = DomNode(
        id="group1",
        role=NodeRole.GROUP,
        text="Group",
        type=NodeType.OTHER,
        children=[button1, text_node, button2],
        attributes=None,
        computed_attributes=ComputedDomAttributes(),
    )
    # Test flatten with all nodes
    flattened = group.flatten()
    assert len(flattened) == 4  # group + 3 children
    assert group in flattened
    assert button1 in flattened
    assert button2 in flattened
    assert text_node in flattened

    # Test flatten with only interaction nodes
    interaction_nodes = group.flatten(lambda node: node.is_interaction())
    assert len(interaction_nodes) == 2  # only buttons
    assert button1 in interaction_nodes
    assert button2 in interaction_nodes
    assert text_node not in interaction_nodes
    assert group not in interaction_nodes


def test_html_selector():
    selector = NodeSelectors(
        playwright_selector="button[name='Submit']",
        css_selector="form > button.submit",
        xpath_selector="//form/button[@name='Submit']",
        notte_selector="button[name='Submit']",
        in_iframe=False,
        in_shadow_root=False,
        iframe_parent_css_selectors=[],
        python_selector="button[name='Submit']",
    )
    assert selector.playwright_selector == "button[name='Submit']"
    assert selector.css_selector == "form > button.submit"
    assert selector.xpath_selector == "//form/button[@name='Submit']"


def test_from_unique_selector_strips_only_prefix():
    css_selector = NodeSelectors.from_unique_selector('css=a[href*="css=foo"]')
    xpath_selector = NodeSelectors.from_unique_selector('xpath=//a[contains(text(), "xpath=foo")]')

    assert css_selector.css_selector == 'a[href*="css=foo"]'
    assert css_selector.playwright_selector is None
    assert xpath_selector.xpath_selector == '//a[contains(text(), "xpath=foo")]'
    assert xpath_selector.playwright_selector is None


def test_node_attributes():
    pre_attrs = DomAttributes.safe_init(
        modal=True,
        required=True,
        description="Test description",
        visible=True,
        selected=False,
        checked=True,
        enabled=True,
        value="test",
        focused=True,
        autocomplete="test",
        haspopup=True,
        disabled=False,
        valuemin="1",
        valuemax="10",
        pressed=True,
        type="text",
        tag_name="button",
        class_name="btn",
        href="https://example.com",
        src="https://example.com/image.jpg",
        srcset="https://example.com/image.jpg 1x, https://example.com/image.jpg 2x",
        target="_blank",
        placeholder="Enter text",
        title="Example",
        alt="Example image",
        name="Example",
        width=100,
        height=100,
        size=100,
        lang="en",
        dir="ltr",
        accesskey="a",
        autofocus=True,
        aria_label="aria_label",
        aria_labelledby="aria_labelledby",
        aria_describedby="aria_describedby",
        aria_hidden=True,
        aria_expanded=True,
        aria_controls="aria_controls",
        aria_haspopup=True,
        action="click",
        role="button",
    )
    assert pre_attrs.modal is True
    assert pre_attrs.required is True
    assert pre_attrs.description == "Test description"

    # Test NotteAttributesPost
    selector = NodeSelectors(
        css_selector="test",
        xpath_selector="test",
        notte_selector="test",
        in_iframe=False,
        in_shadow_root=False,
        iframe_parent_css_selectors=[],
        playwright_selector="test",
        python_selector="test",
    )
    post_attrs = ComputedDomAttributes(selectors=selector)
    assert post_attrs.selectors == selector


def test_all_interaction_roles_have_short_id():
    for role in NodeRole:
        if role.is_interactive():
            assert role.short_id() is not None, f"Role {role.value} has no short id"


@pytest.mark.parametrize(
    ("tag", "attributes", "role"),
    [
        ("a", {}, NodeRole.LINK),
        ("BUTTON", {}, NodeRole.BUTTON),
        ("input", {}, NodeRole.TEXTBOX),
        ("input", {"type": "Checkbox"}, NodeRole.CHECKBOX),
        ("input", {"type": "submit"}, NodeRole.BUTTON),
        ("input", {"type": "search"}, NodeRole.SEARCHBOX),
        ("h3", {}, NodeRole.HEADING),
        ("body", {}, NodeRole.WEBAREA),
        ("iframe", {}, NodeRole.IFRAME),
        ("my-menu-item", {}, NodeRole.MENUITEM),
        ("x-menuitem-checkbox", {}, NodeRole.MENUITEMCHECKBOX),
        ("foo-popup", {}, NodeRole.MENULISTPOPUP),
        ("custom-element", {}, NodeRole.GENERIC),
        ("", {}, NodeRole.NONE),
        # the role attribute wins over the tag
        ("div", {"role": "button"}, NodeRole.BUTTON),
        ("a", {"role": "presentation"}, NodeRole.PRESENTATION),
        ("div", {"role": ""}, NodeRole.GROUP),
        ("div", {"role": "doc-chapter"}, "doc-chapter"),
    ],
)
def test_node_role_from_element(tag: str, attributes: dict[str, str], role: NodeRole | str) -> None:
    assert NodeRole.from_element(tag, attributes) == role
