from collections import defaultdict

from loguru import logger

from notte.browser.node_type import A11yNode, NodeCategory, NodeRole
from notte.pipe.preprocessing.a11y.traversal import (
    find_all_paths_by_role_and_name,
    list_image_nodes,
    list_interactive_nodes,
)

# class SequentialIdGenerator:
#     def __init__(self, exclude_roles: set[str] | None = None):
#         self.exclude_roles: set[str] = exclude_roles or set()
#         self.id_counter: defaultdict[str, int] = defaultdict(lambda: 1)

#     def generate_id(self, role: NodeRole) -> str | None:
#         id = role.short_id()
#         if id is not None and role.value in self.exclude_roles:
#             logger.warning(f"Role {role} is excluded from ID generation")
#             return None
#         if id is not None:
#             self.id_counter[id] += 1
#             return f"{id}{self.id_counter[id]}"
#         return None

#     def reset(self):
#         self.id_counter.clear()

#     def generate(self, root: A11yNode) -> A11yNode:
#         """
#         Generates sequential IDs for interactive elements in the accessibility tree
#         using depth-first search.
#         """
#         stack = [root]
#         while stack:
#             node = stack.pop()
#             role = NodeRole.from_value(node["role"])
#             if isinstance(role, str):
#                 logger.error(
#                   f"Unsupported role to convert to ID: {node}. Please add this role to the ID generation logic ASAP."
#                 )
#             elif len(node["name"].strip()) > 0:
#                 id = self.generate_id(role)
#                 if id is not None:
#                     node["id"] = id
#             stack.extend(reversed(node.get("children", [])))
#         return root


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
                f"Unsupported role to convert to ID: {node}. Please add this role to the ID generation logic ASAP."
            )
        elif (  # images nodes can have empty names
            len(node["name"].strip()) > 0 or role.value in NodeCategory.IMAGE.roles()
        ) and (only_for is None or role.value in only_for):
            id = role.short_id()
            # if only_for is not None:
            #     logger.info(f"Generating ID for {role} because it is in {only_for}")
            if id is not None:
                node["id"] = f"{id}{id_counter[id]}"
                id_counter[id] += 1
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
            raise ValueError("Reference node does not have an ID")
        matches = find_all_paths_by_role_and_name(target, reference_node["role"], reference_node["name"])
        if len(matches) == 0:
            raise ValueError(f"Processing error in the complex axt for {reference_node}")

        for match in matches:
            assert match[0]["role"] == reference_node["role"]
            assert match[0]["name"] == reference_node["name"]
            existing_id = match[0].get("id")
            if existing_id == ref_id:
                return match[0]
            if existing_id is None:
                match[0]["id"] = ref_id
                return match[0]

        raise ValueError(f"Sync ID issue for {reference_node} not found in target tree: {matches}")

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
        if image_source.get("id") is not None:
            image_target["id"] = image_source["id"]
    return target
