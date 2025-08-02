import pytest
from notte_core.browser.dom_tree import ComputedDomAttributes, DomAttributes, DomNode, NodeSelectors
from notte_core.browser.node_type import NodeCategory, NodeRole, NodeType


def test_node_category_roles():
    # Test INTERACTION roles
    interaction_roles = NodeCategory.INTERACTION.roles()
    assert "button" in interaction_roles
    assert "link" in interaction_roles
    assert "textbox" in interaction_roles

    # Test with group role
    interaction_roles_with_group = NodeCategory.INTERACTION.roles(add_group_role=True)
    assert "group" in interaction_roles_with_group
    assert "generic" in interaction_roles_with_group
    assert "none" in interaction_roles_with_group

    # Test TEXT roles
    text_roles = NodeCategory.TEXT.roles()
    assert "text" in text_roles
    assert "heading" in text_roles
    assert "paragraph" in text_roles


def test_node_role_from_value():
    # Test valid role conversion
    assert NodeRole.from_value("BUTTON") == NodeRole.BUTTON
    assert NodeRole.from_value("TEXT") == NodeRole.TEXT

    # Test invalid role returns string
    assert NodeRole.from_value("invalid_role") == "invalid_role"


def test_node_role_category():
    # Test structural roles
    assert NodeRole.WEBAREA.category() == NodeCategory.STRUCTURAL
    assert NodeRole.GROUP.category() == NodeCategory.STRUCTURAL

    # Test text roles
    assert NodeRole.TEXT.category() == NodeCategory.TEXT
    assert NodeRole.HEADING.category() == NodeCategory.TEXT

    # Test interaction roles
    assert NodeRole.BUTTON.category() == NodeCategory.INTERACTION
    assert NodeRole.LINK.category() == NodeCategory.INTERACTION

    # Test table roles
    assert NodeRole.TABLE.category() == NodeCategory.TABLE
    assert NodeRole.ROW.category() == NodeCategory.TABLE

    # Test list roles
    assert NodeRole.LIST.category() == NodeCategory.LIST
    assert NodeRole.LISTITEM.category() == NodeCategory.LIST


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
    assert parent_node.find("child1") == child_node.to_interaction_node()
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


def test_consistency_node_role_and_category():
    for role in NodeRole:
        assert role.value in role.category().roles(), f"Role {role.value} is not in category {role.category()}"

    for category in NodeCategory:
        for role_str in category.roles():
            role = NodeRole.from_value(role_str)
            assert not isinstance(role, str), f"Role {role_str} is a string"
            assert role.category() == category, f"Role {role_str} has wrong category: {role.category()}"


@pytest.fixture
def nested_graph() -> DomNode:
    return DomNode(
        id=None,
        role=NodeRole.WEBAREA,
        type=NodeType.OTHER,
        text="Root",
        children=[
            DomNode(
                id="B1",
                role=NodeRole.BUTTON,
                text="Button 1",
                type=NodeType.INTERACTION,
                children=[],
                attributes=None,
                computed_attributes=ComputedDomAttributes(),
            ),
            DomNode(
                id="B2",
                role=NodeRole.BUTTON,
                text="Button 2",
                type=NodeType.INTERACTION,
                children=[],
                attributes=None,
                computed_attributes=ComputedDomAttributes(),
            ),
            DomNode(
                id=None,
                role=NodeRole.TEXT,
                text="Some text",
                type=NodeType.TEXT,
                children=[],
                attributes=None,
                computed_attributes=ComputedDomAttributes(),
            ),
            DomNode(
                id=None,
                role=NodeRole.GROUP,
                text="Group",
                type=NodeType.OTHER,
                children=[
                    DomNode(
                        id="B3",
                        role=NodeRole.BUTTON,
                        text="Button 3",
                        type=NodeType.INTERACTION,
                        children=[],
                        attributes=None,
                        computed_attributes=ComputedDomAttributes(),
                    ),
                    DomNode(
                        id=None,
                        role=NodeRole.TEXT,
                        text="Some other text",
                        type=NodeType.TEXT,
                        children=[],
                        attributes=None,
                        computed_attributes=ComputedDomAttributes(),
                    ),
                ],
                attributes=None,
                computed_attributes=ComputedDomAttributes(),
            ),
            DomNode(
                id="B4",
                role=NodeRole.BUTTON,
                text="Button 4",
                type=NodeType.INTERACTION,
                children=[],
                attributes=None,
                computed_attributes=ComputedDomAttributes(),
            ),
            DomNode(
                id=None,
                role=NodeRole.TEXT,
                text="Some text 3",
                type=NodeType.TEXT,
                children=[],
                attributes=None,
                computed_attributes=ComputedDomAttributes(),
            ),
            DomNode(
                id=None,
                role=NodeRole.GROUP,
                text="Group 2",
                type=NodeType.OTHER,
                children=[
                    DomNode(
                        id="L1",
                        role=NodeRole.LINK,
                        text="Link 1",
                        type=NodeType.INTERACTION,
                        children=[],
                        attributes=None,
                        computed_attributes=ComputedDomAttributes(),
                    ),
                    DomNode(
                        id=None,
                        role=NodeRole.TEXT,
                        text="Some text 4",
                        type=NodeType.TEXT,
                        children=[],
                        attributes=None,
                        computed_attributes=ComputedDomAttributes(),
                    ),
                ],
                attributes=None,
                computed_attributes=ComputedDomAttributes(),
            ),
        ],
        attributes=None,
        computed_attributes=ComputedDomAttributes(),
    )


def test_subtree_exclude_all_nodes(nested_graph: DomNode):
    def exclude_all_nodes(node: DomNode) -> bool:
        return False

    filtered_graph = nested_graph.subtree_filter(exclude_all_nodes)
    assert filtered_graph is None


def test_subtree_keep_all_nodes(nested_graph: DomNode):
    def keep_all_nodes(node: DomNode) -> bool:
        return True

    filtered_graph = nested_graph.subtree_filter(keep_all_nodes)
    assert filtered_graph == nested_graph


def test_subtree_keep_one_node(nested_graph: DomNode):
    def exclude_some_nodes(node: DomNode) -> bool:
        return len(node.children) > 0 or node.id == "B2"

    filtered_graph = nested_graph.subtree_filter(exclude_some_nodes)
    assert filtered_graph is not None
    assert filtered_graph.id is None
    assert len(filtered_graph.children) == 3, f"Expected 3 children, got {len(filtered_graph.children)}"
    assert filtered_graph.children[0].id == "B2"
    assert filtered_graph.children[1].role == NodeRole.GROUP
    assert filtered_graph.children[2].role == NodeRole.GROUP


def test_subtree_keep_one_node_2(nested_graph: DomNode):
    def exclude_all_except_B2(node: DomNode) -> bool:
        return "B2" in node.subtree_ids

    filtered_graph = nested_graph.subtree_filter(exclude_all_except_B2)
    assert filtered_graph is not None
    assert filtered_graph.id is None
    assert len(filtered_graph.children) == 1
    assert filtered_graph.children[0].id == "B2"


def test_subtree_keep_some_nodes(nested_graph: DomNode):
    def keep_some_nodes(node: DomNode) -> bool:
        return len(set(["B1", "B2", "B3"]).intersection(node.subtree_ids)) > 0

    filtered_graph = nested_graph.subtree_filter(keep_some_nodes)
    assert filtered_graph is not None
    assert len(filtered_graph.children) == 3
    assert filtered_graph.children[0].id == "B1"
    assert filtered_graph.children[1].id == "B2"
    assert filtered_graph.children[2].role == NodeRole.GROUP
    assert filtered_graph.children[2].children[0].id == "B3"
    assert filtered_graph.find("L1") is None
    assert filtered_graph.find("B4") is None
    assert filtered_graph.find("B5") is None


def test_all_interaction_roles_have_short_id():
    for role in NodeRole:
        if role.category() == NodeCategory.INTERACTION:
            assert role.short_id() is not None, f"Role {role.value} has no short id"


def test_non_intersecting_category_roles():
    def all_except(category: NodeCategory) -> set[str]:
        return set([role for cat in NodeCategory if cat.value != category.value for role in cat.roles()])

    for category in NodeCategory:
        _all = all_except(category)
        cat_roles = category.roles()
        assert len(cat_roles.intersection(_all)) == 0, f"Category {category.value} has intersecting roles"
