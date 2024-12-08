"""
Validation functions for a11y trees
I.e. checking consistency between two ax trees (i.e all IDs are unique and consistent across trees)
"""

from notte.browser.node_type import A11yNode
from notte.pipe.preprocessing.a11y.traversal import (
    interactive_list_to_set,
    list_interactive_nodes,
)


def check_consistency(node: A11yNode, other_node: A11yNode, soft: bool = False) -> bool:
    if node == other_node:
        return True

    if not soft:
        return False
    if node["role"] != other_node["role"] or node.get("id") != other_node.get("id"):
        return False
    # one can be a subset of the other
    name1, name2 = node["name"], other_node["name"]
    if name1 in name2 or name2 in name1:
        return True
    return False


def check_interactions_consistency_accross_ax_trees(
    ax_tree: A11yNode,
    other_ax_tree: A11yNode,
    list_all: bool = False,
    soft: bool = False,
    raise_error: bool = False,
    only_with_id: bool = False,
) -> bool:
    ax_tree_interactions = list_interactive_nodes(ax_tree, only_with_id=only_with_id)
    other_ax_tree_interactions = list_interactive_nodes(other_ax_tree, only_with_id=only_with_id)
    if len(ax_tree_interactions) != len(other_ax_tree_interactions) and raise_error:
        iset = interactive_list_to_set(other_ax_tree_interactions)
        oset = interactive_list_to_set(ax_tree_interactions)
        raise ValueError(
            (
                f"#interactions in ax tree       = {len(ax_tree_interactions)}, "
                f"#interactions in other ax tree = {len(other_ax_tree_interactions)} "
                f"#diff = {iset.difference(oset)}"
            )
        )
    errors: list[str] = []
    for a, b in zip(ax_tree_interactions, other_ax_tree_interactions):
        if not check_consistency(a, b, soft=soft):
            error = f"Identifaction issue detected between ax trees: {a} != {b}"
            if list_all:
                errors.append(error)
            elif raise_error:
                raise ValueError(error)
            else:
                print(error)

    if len(errors) > 0 and raise_error:
        raise ValueError("\n".join(errors))

    return len(errors) == 0
