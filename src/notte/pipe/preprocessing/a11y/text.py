from loguru import logger

from notte.browser.dom_tree import A11yNode
from notte.browser.node_type import NodeCategory
from notte.pipe.preprocessing.a11y.grouping import group_following_text_nodes
from notte.pipe.preprocessing.a11y.traversal import flatten_node

DISABLED_TEXT_FIELDS = set([""])


def compute_only_text_roles(node: A11yNode) -> A11yNode:
    is_text_role = node["role"] in NodeCategory.TEXT.roles(add_group_role=True)
    node["only_text_roles"] = is_text_role
    if "children" not in node:
        return node
    for child in node["children"]:
        child = compute_only_text_roles(child)
        node["only_text_roles"] = node["only_text_roles"] and child.get("only_text_roles", False)
    return node


def prune_text_field_already_contained_in_parent_name(node: A11yNode) -> A11yNode:
    """
    Prune a text field if it is already contained in the parent node's name to reduce redundancy.

    Example:
    group {
        heading "New iPhone 16 Pro" {
            text "New"
            text "iPhone 16 Pro"
        }
        text "Available in Desert Titanium, Natural Titanium, Black Titanium, and White Titanium"
    }

    Should be pruned to:
    group {
        heading "New iPhone 16 Pro"
        text "Available in Desert Titanium, Natural Titanium, Black Titanium, and White Titanium"
    }
    """
    children: list[A11yNode] | None = node.get("children")
    if children is None:
        return node

    pruned_children: list[A11yNode] = []
    parent_name = node["name"]
    for child in children:
        # TODO: do the same for all other text roles, i.e. NodeCategory.TEXT.roles()
        # IIF this occurs at least once in a real case environment, we should add it here
        if child["role"] == "text":
            if child["name"] in parent_name or child["name"] in DISABLED_TEXT_FIELDS:
                logger.debug(f"Pruning text field '{child['name']}' already contained in parent name '{parent_name}'")
            else:
                pruned_children.append(child)
        else:
            pruned_children.append(prune_text_field_already_contained_in_parent_name(child))
    if len(pruned_children) == 0 or (len(pruned_children) == 1 and pruned_children[0]["role"] == "LineBreak"):
        del node["children"]
    else:
        node["children"] = pruned_children
    return node


def fold_paragraph_single_text_node(node: A11yNode) -> A11yNode:
    """
    Fold a paragraph node with a single text node into a text node.

    Example:
    paragraph {
        text "Take a closer look at"
    }

    Should be folded to:
    text "\nTake a closer look at\n"

    Note that we add a newline character at the beginning and end of the text node (property of a paragraph)
    """
    if "children" not in node:
        return node
    children: list[A11yNode] = node["children"]
    if node["role"] == "paragraph" and len(children) == 1 and children[0]["role"] == "text":
        # Change
        node["name"] = children[0]["name"] + "\n"
        node["role"] = "text"
        del node["children"]
    else:
        node["children"] = [fold_paragraph_single_text_node(child) for child in children]

    return node


def flatten_group_with_only_text_children(node: A11yNode) -> A11yNode:
    if "children" not in node:
        return node

    new_children: list[A11yNode] = []
    for child in node["children"]:
        if child["role"] == "group" and child.get("only_text_roles", False):
            new_children.extend(flatten_node(child))
        else:
            new_children.append(flatten_group_with_only_text_children(child))
    node["children"] = new_children
    return node


def convert_only_text_subtree_to_markdown(node: A11yNode) -> A11yNode:
    logger.debug("Converting only text subtree to markdown: not implemented")
    return node


def prune_text_nodes(node: A11yNode) -> A11yNode:
    node = compute_only_text_roles(node)
    ft = [
        prune_text_field_already_contained_in_parent_name,
        flatten_group_with_only_text_children,
        group_following_text_nodes,
        fold_paragraph_single_text_node,
        # convert_only_text_subtree_to_markdown,
    ]
    for f in ft:
        node = f(node)
    return node
