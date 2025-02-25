import pytest

from notte.browser.dom_tree import A11yNode
from notte.pipe.preprocessing.a11y.id_generation import generate_sequential_ids, sync_ids_between_trees


def create_test_tree() -> A11yNode:
    """Creates a test accessibility tree with nested nodes"""
    return {
        "role": "main",
        "name": "Main content",
        "children": [
            {"role": "button", "name": "Submit", "children": []},
            {"role": "textbox", "name": "Username", "children": []},
            {
                "role": "group",
                "name": "Navigation",
                "children": [
                    {"role": "link", "name": "Home", "children": []},
                    {"role": "link", "name": "About", "children": []},
                ],
            },
            {"role": "button", "name": "Cancel", "children": []},
            {"role": "link", "name": "About", "children": []},
        ],
    }


def test_generate_sequential_ids():
    """Test that sequential IDs are generated correctly for interactive elements"""
    tree = create_test_tree()
    processed_tree = generate_sequential_ids(tree)

    # Check that non-interactive elements don't get IDs
    assert "id" not in processed_tree  # main role
    assert "id" not in processed_tree["children"][2]  # group role

    # Check that interactive elements get correct sequential IDs
    submit_button = processed_tree["children"][0]
    assert submit_button["id"] == "B1"

    username_input = processed_tree["children"][1]
    assert username_input["id"] == "I1"

    home_link = processed_tree["children"][2]["children"][0]
    assert home_link["id"] == "L1"

    about_link = processed_tree["children"][2]["children"][1]
    assert about_link["id"] == "L2"

    cancel_button = processed_tree["children"][3]
    assert cancel_button["id"] == "B2"

    about_link_2 = processed_tree["children"][4]
    assert about_link_2["id"] == "L3"


def test_sync_ids_between_trees():
    """Test that IDs are correctly synchronized between two trees"""
    # Create source tree with IDs
    source_tree = create_test_tree()
    source_tree = generate_sequential_ids(source_tree)

    # Create target tree (same structure but without IDs)
    target_tree = create_test_tree()

    # Sync IDs
    processed_tree = sync_ids_between_trees(target_tree, source_tree)

    # Verify that IDs match between source and target trees
    def verify_ids(source_node: A11yNode, target_node: A11yNode):
        if "id" in source_node:
            assert "id" in target_node
            assert source_node["id"] == target_node["id"]

        source_children = source_node.get("children", [])
        target_children = target_node.get("children", [])

        for s_child, t_child in zip(source_children, target_children):
            verify_ids(s_child, t_child)

    verify_ids(source_tree, processed_tree)


def test_sync_ids_with_missing_node():
    """Test that sync_ids_between_trees raises an error when a node is missing"""
    source_tree = create_test_tree()
    source_tree = generate_sequential_ids(source_tree)

    # Create target tree with a missing node
    target_tree = create_test_tree()
    target_tree["children"].pop(0)  # Remove the first button

    with pytest.raises(ValueError, match="Processing error in the complex axt for"):
        sync_ids_between_trees(target_tree, source_tree)


def test_generate_ids_with_empty_names():
    """Test that nodes with empty names don't get IDs"""
    tree: A11yNode = {
        "role": "main",
        "name": "",
        "children": [
            {"role": "button", "name": "", "children": []},  # Empty name
            {"role": "button", "name": "Valid Button", "children": []},
        ],
    }

    processed_tree = generate_sequential_ids(tree)

    # Button with empty name should not have an ID
    assert "id" not in processed_tree["children"][0]

    # Button with valid name should have an ID
    assert processed_tree["children"][1]["id"] == "B1"


def test_generate_ids_with_unsupported_role():
    """Test handling of unsupported roles"""
    tree: A11yNode = {
        "role": "main",
        "name": "Main",
        "children": [{"role": "unsupported_role", "name": "Test", "children": []}],  # Invalid role
    }

    # Should not raise an error, but log a warning
    processed_tree = generate_sequential_ids(tree)
    assert "id" not in processed_tree["children"][0]
