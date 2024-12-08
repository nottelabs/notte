from loguru import logger
from notte.browser.node_type import A11yNode
from notte.pipe.preprocessing.a11y.traversal import (
    find_all_paths_by_role_and_name,
    list_interactive_nodes,
)


def generate_sequential_ids(root: A11yNode) -> A11yNode:
    """
    Generates sequential IDs for interactive elements in the accessibility tree
    using depth-first search.
    """
    stack = [root]
    link_id = 1
    button_id = 1
    interaction_id = 1

    while stack:
        node = stack.pop()
        children = node.get("children", [])
        if node["role"] == "link":
            node["id"] = f"L{link_id}"
            link_id += 1
        elif node["role"] in ["button", "tab"]:
            node["id"] = f"B{button_id}"
            button_id += 1
        elif node["role"] in [
            "combobox",
            "listbox",
            "textbox",
            "checkbox",
            "radio",
            "searchbox",
        ]:
            node["id"] = f"I{interaction_id}"
            interaction_id += 1
        elif len(children) == 0 and node["role"] not in [
            "text",
            "heading",
            "group",
            "none",
            "generic",
            "Iframe",
        ]:
            logger.error(f"Unsupported role to convert to ID: {node}. Please fix this ASAP.")
            pass
            # raise ValueError(f'unsupported role to convert to ID: {node}')
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
            existing_id = match[0].get("id")
            if existing_id == ref_id:
                return match[0]
            if existing_id is None:
                match[0]["id"] = ref_id
                return match[0]

        raise ValueError(f"ID issue for {reference_node}")

    interactions = list_interactive_nodes(source)
    for interaction in interactions:
        _ = add_id(interaction)
    return target
