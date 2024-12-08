from notte.browser.node_type import A11yNode, NodeCategory

# TODO: disabled for now because it creates some issues with text grouping
# requires more work and testing
# from .grouping import group_a11y_node
from notte.pipe.preprocessing.a11y.utils import add_group_role


def prune_empty_links(node: A11yNode) -> A11yNode | None:
    if node.get("role") == "link" and node.get("name") in ["", "#"]:
        return None

    children: list[A11yNode] = []
    for child in node.get("children", []):
        pruned_child = prune_empty_links(child)
        if pruned_child is not None:
            children.append(pruned_child)
    node["children"] = children
    return node


def prune_text_child_in_interaction_nodes(node: A11yNode) -> A11yNode:
    # raise NotImplementedError("Not implemented")
    children: list[A11yNode] = node.get("children", [])
    if (
        node.get("role") in NodeCategory.INTERACTION.roles()
        and len(children) == 1
        and children[0].get("role") in NodeCategory.TEXT.roles()
    ):
        node["children"] = []
        return node

    node["children"] = [prune_text_child_in_interaction_nodes(child) for child in children]
    return node


def fold_link_button(node: A11yNode) -> A11yNode:
    children: list[A11yNode] = node.get("children", [])
    if node.get("role") == "link" and len(children) == 1 and children[0].get("role") == "button":
        node["children"] = []
        return node

    node["children"] = [fold_link_button(child) for child in children]
    return node


def nb_real_children(node: A11yNode) -> int:
    return len([child for child in node.get("children", []) if is_interesting(child, prune_text_nodes=True)])


def is_interesting(
    node: A11yNode,
    prune_images: bool = True,
    prune_text_nodes: bool = False,
) -> bool:
    """
    A node is interesting if it is a text node with a non empty name

    Images are not considered interesting for the purpose of NOTTE
    """
    if prune_images and node.get("role") in ["image", "img"]:
        return False
    if node.get("role") == "text":
        if prune_text_nodes:
            return False
        name = node.get("name", "")
        return len(name.strip() if name else "") > 0
    if node.get("role") in NodeCategory.INTERACTION.roles():
        return True
    if node.get("role") in NodeCategory.PARAMETERS.roles():
        return True
    return node.get("role") != "none" and node.get("name") != ""


def prune_non_interesting_nodes(node: A11yNode) -> A11yNode | None:
    children: list[A11yNode] = []
    for child in node.get("children", []):
        pruned_child = prune_non_interesting_nodes(child)
        if pruned_child is not None:
            children.append(pruned_child)

    if not is_interesting(node) and len(children) == 0:
        return None
    node["children"] = children
    return node


def prune_simple_accessiblity_tree(node: A11yNode) -> A11yNode | None:
    pipe = [
        fold_link_button,
        prune_non_interesting_nodes,
        prune_empty_links,
        prune_text_child_in_interaction_nodes,
        # TODO: disable for now because on google flights it creates
        # some issue with buttons reordering
        # [button] 'More information on suggested flights.'  (B9)
        # group_following_text_nodes,
    ]
    _node: A11yNode | None = node
    for step in pipe:
        _node = step(_node)  # type: ignore
        if _node is None:
            return None
    return _node


def prune_accessiblity_tree(node: A11yNode) -> A11yNode:

    def add_children_to_pruned_node(node: A11yNode, children: list[A11yNode]) -> A11yNode:
        node["children"] = children
        # return group_a11y_node(node)
        return node

    def filter_node(node: A11yNode) -> bool:
        if node.get("children") and len(node.get("children", [])) > 0:
            return True
        # removes all nodes with 'role' == 'none' and no children
        return is_interesting(node)

    def prioritize_role(child: A11yNode) -> tuple[str, str]:
        low_priority_roles = ["none", "generic", "group"]
        node_role = node["role"]
        child_role = child["role"]
        if node_role == child_role:
            return node_role, ""
        match (node_role in low_priority_roles, child_role in low_priority_roles):
            case (True, True):
                return "group", ""
            case (True, False):
                return child_role, ""
            case (False, True):
                return node_role, ""
            case (False, False):
                if node_role in ["listitem", "paragraph", "main"]:
                    return child_role, node_role
                if child_role in ["list", "paragraph"]:
                    return node_role, child_role
                # always prioritize links, buttons and text (i.e interactive elements)
                if child_role in NodeCategory.INTERACTION.roles() or child_role == "text":
                    return child_role, node_role
                return child_role, node_role
        raise ValueError(f"No priority found for {node_role} and {child_role}")

    base: A11yNode = {
        "role": node["role"],
        "name": node["name"],
    }
    if not node.get("children"):
        return base
    # if there is only one child and the note is not interesting, skip it
    pruned_children = [prune_accessiblity_tree(child) for child in node.get("children", []) if filter_node(child)]
    # scond round of filtrering
    pruned_children = [child for child in pruned_children if filter_node(child)]

    if len(pruned_children) == 0:
        return base

    def fold_single_child(child: A11yNode) -> A11yNode:
        if not is_interesting(node):
            child["role"], group_role = prioritize_role(child)
            if group_role:
                child = add_group_role(child, group_role)
            return child
        # now we check in the children is a text and check
        # if the current node has the same name
        if child.get("role") in ["text", "heading"] and child.get("name") == base["name"]:
            return base
        # if the node is a link and the child is a button
        # with same text => return button
        if base.get("role") == "link" and child.get("role") == "button" and child.get("name") == base.get("name"):
            node["children"] = []
            return node

        if child.get("role") in ["group", "none", "generic"]:
            if not child.get("children"):
                raise ValueError(f"Group nodes should have children: {child}")
            children = child.get("children", [])
        else:
            children = [child]

        return add_children_to_pruned_node(base, children)

    if len(pruned_children) == 1:
        return fold_single_child(pruned_children[0])

    if base["role"] in ["none", "generic"]:
        base["role"] = "group"
    # compute children_roles
    return add_children_to_pruned_node(base, pruned_children)


# ####################################################################################
# ############################ PRUNING IDEAS #########################################
# ####################################################################################


# TODO: if node has only 2 children (one text, and one other) but 'name' == 'text' => remove text node
# [WebArea] 'Instagram'
# ├── [article as main] ''
# │   ├── [group] ''
# │   │   ├── [heading] 'Instagram'
# │   │   └── [group] ''
# │   │       ├── [group] ''
# │   │       │   ├── [LabelText] ''
# │   │       │   │   ├── [text] 'Phone number, username or email address'
# │   │       │   │   └── [textbox] 'Phone number, username or email address'  (I1)
# │   │       │   ├── [LabelText] ''
# │   │       │   │   ├── [text] 'Password'
# │   │       │   │   └── [textbox] 'Password'  (I2)
# │   │       │   ├── [button] 'Log in'  (B1)
# │   │       │   ├── [text] 'OR'
# │   │       │   └── [button] 'Log in with Facebook Log in with Facebook'  (B2)
# │   │       └── [link] 'Forgotten your password?'  (L1)
def prune_duplicated_text_nodes(node: A11yNode) -> A11yNode | None:
    children = node.get("children", [])
    if len(children) == 2:
        role0, role1 = children[0]["role"], children[1]["role"]
        if role0 == "text" and role1 != "text":
            if children[0]["name"] == children[1]["name"]:
                node["children"] = [children[1]]
            elif role1 == "text" and role0 != "text":
                if children[1]["name"] == children[0]["name"]:
                    node["children"] = [children[0]]

    new_children = [prune_duplicated_text_nodes(child) for child in children]
    node["children"] = [child for child in new_children if child is not None]
    return node
