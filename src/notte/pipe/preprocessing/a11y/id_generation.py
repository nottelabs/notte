from collections import defaultdict

from loguru import logger

from notte.browser.dom_tree import A11yNode
from notte.browser.node_type import NodeCategory, NodeRole
from notte.errors.processing import InconsistentInteractionsNodesInAxTrees
from notte.pipe.preprocessing.a11y.traversal import (
    find_all_paths_by_role_and_name,
    list_image_nodes,
    list_interactive_nodes,
)
from notte.pipe.preprocessing.dom.types import DOMBaseNode, DOMElementNode


def as_dict(node: A11yNode | DOMBaseNode) -> A11yNode:
    if isinstance(node, dict):
        return node
    return {
        "role": node.role,
        "name": node.name,
        "is_interactive": node.is_interactive if isinstance(node, DOMElementNode) else False,
        "children": [as_dict(child) for child in node.children],
    }


def set_id(node: A11yNode | DOMBaseNode, id: str) -> None:
    if isinstance(node, dict):
        node["id"] = id
    else:
        node.notte_id = id


def get_children(node: A11yNode | DOMBaseNode) -> list[A11yNode] | list[DOMBaseNode]:
    if isinstance(node, dict):
        return node.get("children", [])
    return node.children


def generate_sequential_ids(root: A11yNode, only_for: set[str] | None = None) -> A11yNode:
    """
    Generates sequential IDs for interactive elements in the accessibility tree
    using depth-first search.
    """
    stack = [root]
    id_counter: defaultdict[str, int] = defaultdict(lambda: 1)
    while stack:
        node = stack.pop()
        children = node.get("children", [])

        role = NodeRole.from_value(node["role"])
        if isinstance(role, str):
            logger.error(
                f"Unsupported role to convert to ID: {node}. Please add this role to the NodeRole e logic ASAP."
            )
        elif (  # images nodes can have empty names
            node.get("is_interactive", False)
            or (len(node["name"].strip()) > 0 or role.value in NodeCategory.IMAGE.roles())
        ) and (only_for is None or role.value in only_for):
            id = role.short_id()
            # logger.info(f"Generating ID: {id} for {role} with name {_node['name']}")
            # if only_for is not None:
            #     logger.info(f"Generating ID for {role} because it is in {only_for}")
            if id is not None:
                set_id(node, f"{id}{id_counter[id]}")
                id_counter[id] += 1
        stack.extend(reversed(children))

    return root


def simple_generate_sequential_ids(root: DOMBaseNode) -> DOMBaseNode:
    """
    Generates sequential IDs for interactive elements in the accessibility tree
    using depth-first search.
    """
    stack = [root]
    id_counter: defaultdict[str, int] = defaultdict(lambda: 1)
    while stack:
        node = stack.pop()
        children = node.children

        role = NodeRole.from_value(node.role)
        if isinstance(role, str):
            logger.debug(
                f"Unsupported role to convert to ID: {node}. Please add this role to the NodeRole e logic ASAP."
            )
        elif node.highlight_index is not None:
            id = role.short_id(force_id=True)
            if id is not None:
                node.notte_id = f"{id}{id_counter[id]}"
                id_counter[id] += 1
            else:
                raise ValueError(
                    (
                        f"Role {role} was incorrectly converted from raw Dom Node."
                        " It is an interaction node. It should have a short ID but is currently None"
                    )
                )
        stack.extend(reversed(children))

    return root


def sync_ids_between_trees(target: A11yNode, source: A11yNode) -> A11yNode:
    """
    Synchronizes IDs between two accessibility trees by copying IDs from the source
    tree to matching nodes in the target tree.
    """

    def add_id(reference_node: A11yNode) -> A11yNode:
        ref_id = reference_node.get("id")
        if ref_id is None:
            raise InconsistentInteractionsNodesInAxTrees(
                check=(
                    f"Reference node(role='{reference_node['role']}', name='{reference_node['name']}') "
                    "does not have an ID. This cannot happen."
                )
            )
        matches = find_all_paths_by_role_and_name(target, reference_node["role"], reference_node["name"])
        if len(matches) == 0:
            raise InconsistentInteractionsNodesInAxTrees(
                check=(
                    f"Processing error in the complex axt for {reference_node}. "
                    f"No matches found for reference node(role='{reference_node['role']}', "
                    f"name='{reference_node['name']}') in target tree."
                )
            )

        for match in matches:
            assert match[0]["role"] == reference_node["role"]
            assert match[0]["name"] == reference_node["name"]
            existing_id = match[0].get("id")
            if existing_id == ref_id:
                return match[0]
            if existing_id is None:
                match[0]["id"] = ref_id
                return match[0]

        raise InconsistentInteractionsNodesInAxTrees(
            f"Sync ID issue for {reference_node} not found in target tree: {matches}"
        )

    interactions = list_interactive_nodes(source)
    for interaction in interactions:
        _ = add_id(interaction)
    # do the same for images
    images = list_image_nodes(source)
    for image in images:
        if image.get("id") is None:
            _ = add_id(image)
    return target


def sync_image_ids_between_trees(target: A11yNode, source: A11yNode) -> A11yNode:
    images_source = list_image_nodes(source)
    images_target = list_image_nodes(target)
    if len(images_source) != len(images_target):
        # TODO: fix this
        logger.error(
            (
                "Number of images in source and target trees do not match: "
                f"{len(images_source)} != {len(images_target)} "
                f"source: {[(image.get('id'), image['role'], image['name']) for image in images_source]} "
                f"target: {[(image.get('id'), image['role'], image['name']) for image in images_target]}"
            )
        )
    for image_source, image_target in zip(images_source, images_target):
        img_source_id = image_source.get("id")
        if img_source_id is not None:
            image_target["id"] = img_source_id
    return target
