import pytest
from notte.browser.node_type import (
    HtmlSelector,
    NodeAttributesPre,
    NodeCategory,
    NodeRole,
    NotteAttributesPost,
    NotteNode,
)


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
    child_node = NotteNode(
        id="child1",
        role=NodeRole.BUTTON,
        text="Click me",
        attributes_pre=NodeAttributesPre(visible=True),
    )

    parent_node = NotteNode(
        id="parent1",
        role=NodeRole.GROUP,
        text="Parent Group",
        children=[child_node],
    )

    # Test find method
    assert parent_node.find("child1") == child_node
    assert parent_node.find("nonexistent") is None

    # Test is_interaction method
    assert child_node.is_interaction() is True
    assert parent_node.is_interaction() is False

    # Test get_role_str method
    assert child_node.get_role_str() == "button"
    assert parent_node.get_role_str() == "group"

    # Test string role
    string_role_node = NotteNode(id="str1", role="custom_role", text="Custom")
    assert string_role_node.get_role_str() == "custom_role"
    assert string_role_node.is_interaction() is False


def test_notte_node_flatten():
    # Create a nested structure
    button1 = NotteNode(id="btn1", role=NodeRole.BUTTON, text="Button 1")
    button2 = NotteNode(id="btn2", role=NodeRole.BUTTON, text="Button 2")
    text_node = NotteNode(id="txt1", role=NodeRole.TEXT, text="Some text")

    group = NotteNode(id="group1", role=NodeRole.GROUP, text="Group", children=[button1, text_node, button2])

    # Test flatten with all nodes
    flattened = group.flatten(only_interaction=False)
    assert len(flattened) == 4  # group + 3 children
    assert group in flattened
    assert button1 in flattened
    assert button2 in flattened
    assert text_node in flattened

    # Test flatten with only interaction nodes
    interaction_nodes = group.flatten(only_interaction=True)
    assert len(interaction_nodes) == 2  # only buttons
    assert button1 in interaction_nodes
    assert button2 in interaction_nodes
    assert text_node not in interaction_nodes
    assert group not in interaction_nodes


def test_html_selector():
    selector = HtmlSelector(
        playwright_selector="button[name='Submit']",
        css_selector="form > button.submit",
        xpath_selector="//form/button[@name='Submit']",
    )
    assert selector.playwright_selector == "button[name='Submit']"
    assert selector.css_selector == "form > button.submit"
    assert selector.xpath_selector == "//form/button[@name='Submit']"


def test_node_attributes():
    # Test NodeAttributesPre
    pre_attrs = NodeAttributesPre(
        modal=True,
        required=True,
        description="Test description",
        visible=True,
        selected=False,
        checked=True,
        enabled=True,
        path="/path/to/node",
    )
    assert pre_attrs.modal is True
    assert pre_attrs.required is True
    assert pre_attrs.description == "Test description"

    # Test NotteAttributesPost
    selector = HtmlSelector("test", "test", "test")
    post_attrs = NotteAttributesPost(selectors=selector, editable=True, input_type="text", text="Sample text")
    assert post_attrs.editable is True
    assert post_attrs.input_type == "text"
    assert post_attrs.text == "Sample text"


def test_consistency_node_role_and_category():

    for role in NodeRole:
        assert role.value in role.category().roles()

    for category in NodeCategory:
        for role_str in category.roles():
            role = NodeRole.from_value(role_str)
            assert not isinstance(role, str), f"Role {role_str} is a string"
            assert role.category() == category, f"Role {role_str} has wrong category: {role.category()}"


@pytest.fixture
def nested_graph() -> NotteNode:
    return NotteNode(
        id=None,
        role=NodeRole.WEBAREA,
        text="Root",
        children=[
            NotteNode(id="B1", role=NodeRole.BUTTON, text="Button 1"),
            NotteNode(id="B2", role=NodeRole.BUTTON, text="Button 2"),
            NotteNode(id=None, role=NodeRole.TEXT, text="Some text"),
            NotteNode(
                id=None,
                role=NodeRole.GROUP,
                text="Group",
                children=[
                    NotteNode(id="B3", role=NodeRole.BUTTON, text="Button 3"),
                    NotteNode(id=None, role=NodeRole.TEXT, text="Some other text"),
                ],
            ),
            NotteNode(id="B4", role=NodeRole.BUTTON, text="Button 4"),
            NotteNode(id=None, role=NodeRole.TEXT, text="Some text 3"),
            NotteNode(
                id=None,
                role=NodeRole.GROUP,
                text="Group 2",
                children=[
                    NotteNode(id="L1", role=NodeRole.LINK, text="Link 1"),
                    NotteNode(id=None, role=NodeRole.TEXT, text="Some text 4"),
                ],
            ),
        ],
    )


def test_subtree_exclude_all_nodes(nested_graph: NotteNode):
    def exclude_all_nodes(node: NotteNode) -> bool:
        return False

    filtered_graph = nested_graph.subtree_filter(exclude_all_nodes)
    assert filtered_graph is None


def test_subtree_keep_all_nodes(nested_graph: NotteNode):
    def keep_all_nodes(node: NotteNode) -> bool:
        return True

    filtered_graph = nested_graph.subtree_filter(keep_all_nodes)
    assert filtered_graph == nested_graph


def test_subtree_keep_one_node(nested_graph: NotteNode):
    def exclude_some_nodes(node: NotteNode) -> bool:
        return len(node.children) > 0 or node.id == "B2"

    filtered_graph = nested_graph.subtree_filter(exclude_some_nodes)
    assert filtered_graph is not None
    assert filtered_graph.id is None
    assert len(filtered_graph.children) == 3, f"Expected 3 children, got {len(filtered_graph.children)}"
    assert filtered_graph.children[0].id == "B2"
    assert filtered_graph.children[1].role == NodeRole.GROUP
    assert filtered_graph.children[2].role == NodeRole.GROUP


def test_subtree_keep_one_node_2(nested_graph: NotteNode):
    def exclude_all_except_B2(node: NotteNode) -> bool:
        return "B2" in node.subtree_ids

    filtered_graph = nested_graph.subtree_filter(exclude_all_except_B2)
    assert filtered_graph is not None
    assert filtered_graph.id is None
    assert len(filtered_graph.children) == 1
    assert filtered_graph.children[0].id == "B2"


def test_subtree_keep_some_nodes(nested_graph: NotteNode):
    def keep_some_nodes(node: NotteNode) -> bool:
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
