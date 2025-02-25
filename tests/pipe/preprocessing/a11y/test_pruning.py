import pytest

from notte.browser.dom_tree import A11yNode
from notte.pipe.preprocessing.a11y.pruning import (
    PruningConfig,
    fold_link_button,
    prune_empty_links,
    prune_non_interesting_nodes,
    prune_text_child_in_interaction_nodes,
)


@pytest.fixture
def config() -> PruningConfig:
    return PruningConfig(
        prune_texts=False,
        prune_images=True,
    )


def test_fold_link_button():
    # Test case 1: Link with button child should be folded
    link_with_button: A11yNode = {
        "role": "link",
        "name": "Click me",
        "children": [{"role": "button", "name": "Click me", "children": []}],
    }
    assert fold_link_button(link_with_button) == {
        "role": "link",
        "name": "Click me",
        "children": [],
    }

    # Test case 2: Link with non-button child should remain unchanged
    link_with_non_button: A11yNode = {
        "role": "link",
        "name": "Click me",
        "children": [{"role": "text", "name": "Click me", "children": []}],
    }
    assert fold_link_button(link_with_non_button) == link_with_non_button


def test_prune_empty_links(config: PruningConfig):
    # Test case 1: Empty link should be pruned
    empty_link: A11yNode = {"role": "link", "name": "", "children": []}
    assert prune_empty_links(empty_link, config) is None

    # Test case 2: Link with '#' should be pruned
    hash_link: A11yNode = {"role": "link", "name": "#", "children": []}
    assert prune_empty_links(hash_link, config) is None

    # Test case 3: Valid link should remain
    valid_link: A11yNode = {"role": "link", "name": "Click me", "children": []}
    assert prune_empty_links(valid_link, config) == valid_link

    # Test case 4: Node with empty link child should have child pruned
    parent_node: A11yNode = {
        "role": "generic",
        "name": "parent",
        "children": [
            {"role": "link", "name": "", "children": []},
            {"role": "text", "name": "valid text", "children": []},
        ],
    }
    expected: A11yNode = {
        "role": "generic",
        "name": "parent",
        "children": [{"role": "text", "name": "valid text", "children": []}],
    }
    assert prune_empty_links(parent_node, config) == expected


def test_prune_text_child_in_interaction_nodes():
    # Test case 1: Button with single text child should have child pruned
    button_node: A11yNode = {
        "role": "button",
        "name": "Click me",
        "children": [{"role": "text", "name": "Click me", "children": []}],
    }
    expected: A11yNode = {
        "role": "button",
        "name": "Click me",
        "children": [],
    }
    pruned = prune_text_child_in_interaction_nodes(button_node)
    assert pruned == expected, f"Expected {expected} but got {pruned}"

    # Test case 2: Button with multiple children should remain unchanged
    button_multiple: A11yNode = {
        "role": "button",
        "name": "Complex Button",
        "children": [
            {"role": "text", "name": "Click", "children": []},
            {"role": "image", "name": "icon", "children": []},
        ],
    }
    assert prune_text_child_in_interaction_nodes(button_multiple) == button_multiple

    # Test case 3: Non-interaction node with text child should remain unchanged
    generic_node: A11yNode = {
        "role": "generic",
        "name": "wrapper",
        "children": [{"role": "text", "name": "some text", "children": []}],
    }

    assert prune_text_child_in_interaction_nodes(generic_node) == generic_node


def test_complex_pruning_scenario(config: PruningConfig):
    # Test a more complex tree with multiple levels
    complex_tree: A11yNode = {
        "role": "generic",
        "name": "root",
        "children": [
            {
                "role": "button",
                "name": "Button 1",
                "children": [{"role": "text", "name": "Button 1", "children": []}],
            },
            {
                "role": "link",
                "name": "",
                "children": [{"role": "text", "name": "Empty Link", "children": []}],
            },
            {
                "role": "generic",
                "name": "wrapper",
                "children": [
                    {
                        "role": "button",
                        "name": "Nested Button",
                        "children": [{"role": "text", "name": "Nested Button", "children": []}],
                    }
                ],
            },
        ],
    }

    # First prune empty links
    result = prune_empty_links(complex_tree, config)
    # Then prune text children in interaction nodes
    result = prune_text_child_in_interaction_nodes(result)

    expected: A11yNode = {
        "role": "generic",
        "name": "root",
        "children": [
            {"role": "button", "name": "Button 1", "children": []},
            {
                "role": "generic",
                "name": "wrapper",
                "children": [{"role": "button", "name": "Nested Button", "children": []}],
            },
        ],
    }

    assert result == expected


def test_prune_non_interesting_nodes(config: PruningConfig) -> None:
    # Test case 1: Empty generic node should be pruned
    empty_node: A11yNode = {"role": "none", "name": "", "children": []}
    assert prune_non_interesting_nodes(empty_node, config) is None

    # Test case 2: Text node with empty name should be pruned
    empty_text: A11yNode = {"role": "text", "name": "", "children": []}
    assert prune_non_interesting_nodes(empty_text, config) is None

    # Test case 3: Node with valid text should remain
    valid_text: A11yNode = {"role": "text", "name": "Hello World", "children": []}
    assert prune_non_interesting_nodes(valid_text, config) == valid_text

    # Test case 4: Node with interesting child should keep child
    parent_with_mixed_children: A11yNode = {
        "role": "generic",
        "name": "",
        "children": [
            {"role": "none", "name": "", "children": []},  # Should be pruned
            {"role": "button", "name": "Click me", "children": []},  # Should remain
            {
                "role": "text",
                "name": "",
                "children": [],
            },  # Should be pruned (empty text)
            {"role": "text", "name": "valid text", "children": []},  # Should remain
        ],
    }
    expected: A11yNode = {
        "role": "generic",
        "name": "",
        "children": [
            {"role": "button", "name": "Click me", "children": []},
            {"role": "text", "name": "valid text", "children": []},
        ],
    }
    assert prune_non_interesting_nodes(parent_with_mixed_children, config) == expected

    # Test case 5: Complex nested structure
    complex_node: A11yNode = {
        "role": "generic",
        "name": "wrapper",
        "children": [
            {
                "role": "none",
                "name": "",
                "children": [
                    {"role": "text", "name": "Keep this", "children": []},
                    {"role": "none", "name": "", "children": []},
                ],
            },
            {
                "role": "button",
                "name": "Click me",
                "children": [{"role": "none", "name": "", "children": []}],
            },
        ],
    }
    expected: A11yNode = {
        "role": "generic",
        "name": "wrapper",
        "children": [
            {
                "role": "none",
                "name": "",
                "children": [{"role": "text", "name": "Keep this", "children": []}],
            },
            {"role": "button", "name": "Click me", "children": []},
        ],
    }
    assert prune_non_interesting_nodes(complex_node, config) == expected

    # Test case 6: Image nodes should be considered uninteresting
    node_with_image: A11yNode = {
        "role": "generic",
        "name": "wrapper",
        "children": [
            {"role": "image", "name": "decorative image", "children": []},
            {"role": "text", "name": "Keep this text", "children": []},
        ],
    }
    expected: A11yNode = {
        "role": "generic",
        "name": "wrapper",
        "children": [{"role": "text", "name": "Keep this text", "children": []}],
    }
    assert prune_non_interesting_nodes(node_with_image, config) == expected
