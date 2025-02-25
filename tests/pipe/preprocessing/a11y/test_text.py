import pytest

from notte.browser.dom_tree import A11yNode
from notte.pipe.preprocessing.a11y.text import (
    fold_paragraph_single_text_node,
    prune_text_field_already_contained_in_parent_name,
)


@pytest.fixture
def prunable_text_node() -> A11yNode:
    return {
        "role": "WebArea",
        "name": "",
        "children": [
            {
                "role": "heading",
                "name": "New iPhone 16 Pro",
                "children": [
                    {
                        "role": "text",
                        "name": "New",
                    },
                    {
                        "role": "text",
                        "name": "iPhone 16 Pro",
                    },
                ],
            },
            {
                "role": "link",
                "name": "iPhone 16 Pro",
            },
        ],
    }


@pytest.fixture
def prunable_with_linebreak_text_node() -> A11yNode:
    return {
        "role": "heading",
        "name": "Take a closer look at our latest models.",
        "children": [
            {
                "role": "text",
                "name": "Take a closer look at",
            },
            {
                "role": "LineBreak",
                "name": "",
            },
            {
                "role": "text",
                "name": "our latest models.",
            },
        ],
    }


def test_prune_text_field_already_contained_in_parent_name(
    prunable_text_node: A11yNode,
):
    assert prune_text_field_already_contained_in_parent_name(prunable_text_node) == {
        "role": "WebArea",
        "name": "",
        "children": [
            {
                "role": "heading",
                "name": "New iPhone 16 Pro",
            },
            {
                "role": "link",
                "name": "iPhone 16 Pro",
            },
        ],
    }


def test_prune_text_with_linebreak(prunable_with_linebreak_text_node: A11yNode):
    assert prune_text_field_already_contained_in_parent_name(prunable_with_linebreak_text_node) == {
        "role": "heading",
        "name": "Take a closer look at our latest models.",
    }


def prunable_paragraph_single_text_node() -> A11yNode:
    return {
        "role": "paragraph",
        "name": "",
        "children": [
            {
                "role": "text",
                "name": "Take a closer look at",
            }
        ],
    }


def prunable_group_single_text_node() -> A11yNode:
    return {
        "role": "group",
        "name": "",
        "children": [
            {
                "role": "text",
                "name": "Take a closer look at",
            }
        ],
    }


@pytest.mark.parametrize("node", [prunable_paragraph_single_text_node()])
def test_fold_paragraph_single_text_node(node: A11yNode):
    assert fold_paragraph_single_text_node(node) == {
        "role": "text",
        "name": "Take a closer look at\n",
    }
