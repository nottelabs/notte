from collections.abc import Callable

from loguru import logger

from notte.browser.dom_tree import A11yNode
from notte.browser.node_type import NodeCategory

MatchingFt = Callable[[A11yNode], bool]


def find_node_path_by_predicate(node: A11yNode, matching_ft: MatchingFt) -> list[A11yNode] | None:
    if matching_ft(node):
        return [node]
    for child in node.get("children", []):
        result = find_node_path_by_predicate(child, matching_ft)
        if result:
            result.append(node)
            return result
    return None


def find_node_path_by_role_and_name(node: A11yNode, role: str, name: str) -> list[A11yNode] | None:
    def matching_ft(node: A11yNode) -> bool:
        return node["role"] == role and node["name"] == name

    return find_node_path_by_predicate(node, matching_ft)


def find_all_paths_by_role_and_name(node: A11yNode, role: str, name: str) -> list[list[A11yNode]]:
    if node["role"] == role and node["name"] == name:
        return [[node]]
    all_results: list[list[A11yNode]] = []
    for child in node.get("children", []):
        results = find_all_paths_by_role_and_name(child, role, name)
        for result in results:
            result.append(node)
            all_results.append(result)
    return all_results


def find_node_path_by_id(node: A11yNode, notte_id: str) -> list[A11yNode] | None:
    def matching_ft(node: A11yNode) -> bool:
        return node.get("id") == notte_id

    return find_node_path_by_predicate(node, matching_ft)


def find_all_matching_subtrees_with_parents(node: A11yNode, role: str, name: str | None = None) -> list[A11yNode]:
    if node["role"] == role and (name is None or node["name"] == name):
        return [node]

    node_attr_keys: set[str] = set(node.keys()).difference(["children"])
    node_attrs: dict[str, str] = {k: node[k] for k in node_attr_keys}
    matches: list[A11yNode] = []
    for child in node.get("children", []):
        matching_subtrees = find_all_matching_subtrees_with_parents(child, role, name)
        for subtree in matching_subtrees:
            matches.append({**node_attrs, "children": [subtree]})  # type: ignore[type-assignment]

    return matches


def list_interactive_nodes(
    ax_tree: A11yNode,
    parent_path: str | None = None,
    only_with_id: bool = False,
    include_id: bool = True,
) -> list[A11yNode]:
    interactions: list[A11yNode] = []
    id = ax_tree.get("id")
    if ax_tree["role"] in NodeCategory.INTERACTION.roles() and len(ax_tree["name"].strip()) > 0:
        node: A11yNode = {
            "role": ax_tree["role"],
            "name": ax_tree["name"],
        }

        if only_with_id and id is None:
            logger.warning(
                f"[LIST INTERACTIVE NODES] Skipping {ax_tree['role']} {ax_tree['name']} because it has no id"
            )
            return []

        if include_id and id is not None:
            node["id"] = id
        if parent_path is not None:
            node["path"] = ":".join([parent_path, node["role"], node["name"]])
        interactions.append(node)

    for child in ax_tree.get("children", []):
        if parent_path is not None:
            parent_path = ":".join([parent_path, ax_tree["role"], ax_tree["name"]])
        interactions.extend(
            list_interactive_nodes(child, parent_path, only_with_id=only_with_id, include_id=include_id)
        )

    return interactions


def list_image_nodes(ax_tree: A11yNode) -> list[A11yNode]:
    images: list[A11yNode] = []
    if ax_tree["role"] in ["image", "img"]:
        images.append(ax_tree)
    for child in ax_tree.get("children", []):
        images.extend(list_image_nodes(child))
    return images


def interactive_list_to_set(interactions: list[A11yNode], with_id: bool = False) -> set[tuple[str, str, str]]:
    return set(
        (
            interaction.get("id", "") if with_id else "",
            interaction["role"],
            interaction["name"],
        )
        for interaction in interactions
    )


def set_of_interactive_nodes(ax_tree: A11yNode) -> set[tuple[str, str, str]]:
    interactions = list_interactive_nodes(ax_tree)
    return interactive_list_to_set(interactions, with_id=True)


def flatten_node(node: A11yNode) -> list[A11yNode]:
    """
    Flatten a node with children into a list of terminal nodes.
    """
    if "children" not in node:
        return [node]
    return [fchild for child in node["children"] for fchild in flatten_node(child)]
