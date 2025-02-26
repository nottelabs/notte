from copy import deepcopy
from dataclasses import dataclass, field
from functools import partial

from loguru import logger

from notte.browser.dom_tree import A11yNode
from notte.browser.node_type import NodeCategory
from notte.errors.processing import InvalidInternalCheckError
from notte.pipe.preprocessing.a11y.traversal import (
    find_all_matching_subtrees_with_parents,
    list_interactive_nodes,
)
from notte.pipe.preprocessing.a11y.utils import add_group_role


@dataclass
class PruningConfig:
    prune_images: bool = False
    prune_texts: bool = False
    prune_empty_structurals: bool = True
    # TODO: revisif this assumption
    prune_iframes: bool = True
    prune_roles: set[str] = field(default_factory=lambda: set(["InlineTextBox", "ListMarker", "LineBreak"]))
    verbose: bool = False

    def should_prune(self, node: A11yNode) -> bool:
        """
        A node should be pruned if it is an image or a text node with an empty name
        """

        if node["role"] in NodeCategory.INTERACTION.roles():
            return False
        # check text and images
        if node["role"] in NodeCategory.IMAGE.roles():
            # logger.error(f"---------> pruning image {node.get('role')}")
            return self.prune_images

        is_name_empty = node["name"].strip() == ""
        is_children_empty = len(node.get("children", [])) == 0

        if node["role"] in NodeCategory.TEXT.roles():
            return self.prune_texts or (is_name_empty and is_children_empty)

        if node["role"] in NodeCategory.STRUCTURAL.roles():
            return self.prune_empty_structurals and is_children_empty

        if node["role"] in self.prune_roles:
            return True

        # base case: if the node has children, it is not pruned
        if not is_children_empty:
            return False

        if node["role"] == "Iframe":
            return self.prune_iframes
        if self.verbose:
            if is_name_empty:
                logger.warning(
                    (
                        f"Role `{node['role']}` has an empty name and no children. Please considered adding it to"
                        " `prune_roles`"
                    )
                )
            else:
                logger.error(
                    (
                        f"New pruning edge case for node, with role `{node['role']}`, name `{node['name']}` and empty"
                        " children."
                    )
                )
        # other wise only keep nodes with a non empty name
        return node["role"] == "none" or is_name_empty

    def important_roles(self) -> set[str]:
        base = NodeCategory.INTERACTION.roles()
        if not self.prune_texts:
            base.update(NodeCategory.TEXT.roles())
        if not self.prune_images:
            base.update(NodeCategory.IMAGE.roles())
        return base

    def pruning_roles(self) -> set[str]:
        base = self.prune_roles
        if self.prune_texts:
            base.update(NodeCategory.TEXT.roles())
        if self.prune_images:
            base.update(NodeCategory.IMAGE.roles())
        if self.prune_iframes:
            base.update({"Iframe"})
        return base


# TODO: [#12](https://github.com/nottelabs/notte/issues/12)
# disabled for now because it creates some issues with text grouping
# requires more work and testing


def get_subtree_roles(node: A11yNode, include_root_role: bool = True) -> set[str]:
    roles: set[str] = set([node["role"]]) if include_root_role else set()
    for child in node.get("children", []):
        roles.update(get_subtree_roles(child, include_root_role=True))
    return roles


def prune_non_dialogs_if_present(node: A11yNode) -> A11yNode:
    dialogs = find_all_matching_subtrees_with_parents(node, "dialog")
    # filter those that are not interactive
    interactive_dialogs = [dialog for dialog in dialogs if len(list_interactive_nodes(dialog)) > 0]

    if len(interactive_dialogs) == 0:
        # no dialogs found, return node
        return node
    if len(interactive_dialogs) > 1:
        raise InvalidInternalCheckError(
            check=f"Multiple dialogs found in {node} (unexpected behavior please check this)",
            dev_advice=(
                "We made the assupmtion that there is only one dialog in the tree at any given time. "
                "This may have to be revisited."
            ),
            url=None,
        )
    return interactive_dialogs[0]


def prune_empty_links(node: A11yNode, config: PruningConfig) -> A11yNode | None:
    if node["role"] == "link" and node["name"] in ["", "#"]:
        if len(node.get("children", [])) == 0:
            return None
        # otherwise check if there is an image in the children
        # then we keep the image
        if not config.prune_images:
            for child in node.get("children", []):
                if child["role"] in NodeCategory.IMAGE.roles():
                    return node
        logger.warning(f"Pruning empty link {node['name']} with nb children {len(node.get('children', []))}")
        return None

    children: list[A11yNode] = []
    for child in node.get("children", []):
        pruned_child = prune_empty_links(child, config)
        if pruned_child is not None:
            children.append(pruned_child)
    node["children"] = children
    return node


def prune_text_child_in_interaction_nodes(node: A11yNode, verbose: bool = False) -> A11yNode:
    allowed_roles = NodeCategory.IMAGE.roles()

    children: list[A11yNode] = node.get("children", [])
    if node["role"] in NodeCategory.INTERACTION.roles() and len(children) >= 1 and len(node["name"]) > 0:
        # we can prune the whole subtree if it has only text children
        # and children[0]["role"] in NodeCategory.TEXT.roles()
        other_than_text = get_subtree_roles(node, include_root_role=False).difference(
            NodeCategory.TEXT.roles(add_group_role=True)
        )
        if len(other_than_text) == 0:
            node["children"] = []
            return node
        elif len(other_than_text.difference(allowed_roles)) == 0:
            # images are allowed in interaction nodes
            return node
        else:
            if verbose:
                logger.warning(
                    (
                        f"Found non-text children (i.e. {other_than_text}) in interaction"
                        f" node role {node['role']} and name {node['name']}"
                    )
                )

    node["children"] = [prune_text_child_in_interaction_nodes(child) for child in children]
    return node


def fold_link_button(node: A11yNode) -> A11yNode:
    children: list[A11yNode] = node.get("children", [])
    if node["role"] == "link" and len(children) == 1 and children[0]["role"] == "button":
        node["children"] = []
        return node

    node["children"] = [fold_link_button(child) for child in children]
    return node


def fold_button_in_button(node: A11yNode) -> A11yNode:
    children: list[A11yNode] = node.get("children", [])
    if (
        node["role"] == "button"
        and len(children) == 1
        and children[0]["role"] == "button"
        and node["name"] == children[0]["name"]
    ):
        logger.info(f"Folding button in button with name '{node.get('name')}'")
        node["children"] = children[0].get("children", [])
        return node

    node["children"] = [fold_button_in_button(child) for child in children]
    return node


# def nb_real_children(node: A11yNode, config: PruningConfig) -> int:
#     return len([child for child in node.get("children", []) if is_interesting(child, config)])


def prune_non_interesting_nodes(node: A11yNode, config: PruningConfig) -> A11yNode | None:
    children: list[A11yNode] = []
    for child in node.get("children", []):
        pruned_child = prune_non_interesting_nodes(child, config)
        if pruned_child is not None:
            children.append(pruned_child)

    if config.should_prune(node) and len(children) == 0:
        return None
    node["children"] = children
    return node


# Bottleneck
def deep_copy_node(node: A11yNode) -> A11yNode:
    if node.get("children"):
        node["children"] = [deep_copy_node(child) for child in node.get("children", [])]
    return deepcopy(node)


def simple_processing_accessiblity_tree(node: A11yNode, config: PruningConfig) -> A11yNode | None:
    node = deep_copy_node(node)
    pipe = [
        fold_link_button,
        fold_button_in_button,
        partial(prune_non_interesting_nodes, config=config),
        partial(prune_empty_links, config=config),
        prune_text_child_in_interaction_nodes,
        # TODO: #12
        # disable for now because on google flights it creates
        # some issue with buttons reordering
        # [button] 'More information on suggested flights.'  (B9)
        # group_following_text_nodes,
    ]
    _node: A11yNode | None = node
    for step in pipe:
        _node = step(_node)
        if _node is None:
            return None
    return _node


def complex_processing_accessiblity_tree(node: A11yNode, config: PruningConfig) -> A11yNode:
    node = deep_copy_node(node)

    def add_children_to_pruned_node(node: A11yNode, children: list[A11yNode]) -> A11yNode:
        node["children"] = children
        # TODO: #12
        # return group_a11y_node(node)
        return node

    def keep_node(node: A11yNode) -> bool:
        if node.get("children") and len(node.get("children", [])) > 0:
            return True
        # removes all nodes with 'role' == 'none' and no children
        return not config.should_prune(node)

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
                if child_role in config.important_roles():
                    return child_role, node_role
                return child_role, node_role

    base: A11yNode = deepcopy(node)
    if base.get("children"):
        del base["children"]
    children = node.get("children", [])
    nb_children = len(children)
    if nb_children == 0:
        return base

    # if there is only one child and the note is not interesting, skip it
    pruned_children = [complex_processing_accessiblity_tree(child, config) for child in children if keep_node(child)]
    # scond round of filtrering
    pruned_children = [child for child in pruned_children if keep_node(child)]

    if len(pruned_children) == 0:
        return base

    def fold_single_child(child: A11yNode) -> A11yNode:
        if config.should_prune(node):
            raise InvalidInternalCheckError(
                check=(
                    f"parent node(role='{node['role']}', name='{node['name']}') should have already been "
                    "pruned before reaching this point. "
                ),
                dev_advice="This should not happen. Please check the node and the tree to see why this is happening.",
                url=None,
            )
            # Vestige of the old code (check if we can remove it)
            # child["role"], group_role = prioritize_role(child)
            # if group_role:
            #     child = add_group_role(child, group_role)
            # return child
        if node["name"].strip() == "":
            child["role"], group_role = prioritize_role(child)
            if group_role:
                child = add_group_role(child, group_role)
            return child
        # now we check in the children is a text and check
        # if the current node has the same name
        if child["role"] in NodeCategory.TEXT.roles() and child["name"] in base["name"]:
            return base
        # if the node is a link and the child is a button
        # with same text => return button
        if base["role"] == "link" and child["role"] == "button" and child["name"] == base["name"]:
            node["children"] = []
            return node
        # skip list node
        if child["role"] in NodeCategory.LIST.roles():
            return child

        # skip the structural node
        if child["role"] in NodeCategory.STRUCTURAL.roles():
            if not child.get("children") and child.get("nb_pruned_children") in [None, 0]:
                raise InvalidInternalCheckError(
                    check=(
                        "structural nodes should have children but node "
                        f"(role='{child['role']}', name='{child['name']}') has no children"
                    ),
                    dev_advice=(
                        "The structural nodes have been specically created to highlight nodes that don't really "
                        "have a role except containing other nodes. You should check if this role should indeed "
                        "be a structural node or not. Considered updating `NodeCategory.STRUCTURAL.roles()`."
                    ),
                    url=None,
                )
            # skip the structural node
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
    text_roles = NodeCategory.TEXT.roles()
    if len(children) == 2:
        role0, role1 = children[0]["role"], children[1]["role"]
        if role0 in text_roles and role1 not in text_roles:
            if children[0]["name"] == children[1]["name"]:
                node["children"] = [children[1]]
        elif role1 in text_roles and role0 not in text_roles:
            if children[1]["name"] == children[0]["name"]:
                node["children"] = [children[0]]

    new_children = [prune_duplicated_text_nodes(child) for child in children]
    node["children"] = [child for child in new_children if child is not None]
    return node
