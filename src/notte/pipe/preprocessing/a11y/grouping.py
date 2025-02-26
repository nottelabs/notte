from collections.abc import Callable

from loguru import logger

from notte.browser.dom_tree import A11yNode
from notte.browser.node_type import NodeCategory
from notte.errors.processing import InvalidA11yChildrenError, InvalidInternalCheckError
from notte.pipe.preprocessing.a11y.utils import (
    add_group_role,
    children_roles,
    compute_children_roles,
    inner_compute_children_roles_count,
)


def get_group_func(group_type: NodeCategory) -> Callable[[A11yNode], A11yNode]:
    match group_type:
        case NodeCategory.TEXT:
            return group_text_children
        case NodeCategory.INTERACTION:
            return group_interaction_children
        case NodeCategory.TABLE:
            return group_table_children
        case _:
            raise InvalidInternalCheckError(
                check=f"Unknown group type: {group_type}. Valid group types are: {list(NodeCategory)}",
                dev_advice=(
                    "This should not happen. Someone proably added a new group type without updating properly the code."
                ),
                url=None,
            )


def should_group(node: A11yNode, group_roles: set[str], add_group_role: bool = True) -> bool:
    all_group_roles = set(list(group_roles))
    if add_group_role:
        all_group_roles.update(["group", "generic", "none"])

    def nb_valid_groups(node: A11yNode) -> int:
        if not node.get("children"):
            return node.get("role") in group_roles
        if len(children_roles(node).difference(all_group_roles)) > 0:
            return 0
        # count the number of valid groups in the children
        return sum([node.get("children_roles_count", {}).get(role, 0) for role in group_roles])

    # 2 conditions to be able to group:
    # (a) all children are in the group_roles but not the node itself
    # (b) at least 2 children are in the group_roles but there is at
    # least one child that is not in the group_roles
    nb_invalid_children = sum([nb_valid_groups(child) == 0 for child in node.get("children", [])])
    total_nb_valid_groups = sum([nb_valid_groups(child) for child in node.get("children", [])])

    return (len(children_roles(node).difference(all_group_roles)) == 0 and node.get("role") not in all_group_roles) or (
        total_nb_valid_groups >= 2 and nb_invalid_children >= 1
    )


def is_text_group(node: A11yNode, add_group_role: bool = True) -> bool:
    text_roles = NodeCategory.TEXT.roles(add_group_role=add_group_role)
    if not node.get("children"):
        return node.get("role") in NodeCategory.TEXT.roles(add_group_role=False)
    return len(children_roles(node).difference(text_roles)) == 0


def is_interaction_group(node: A11yNode, add_group_role: bool = True) -> bool:
    interaction_roles = NodeCategory.INTERACTION.roles(add_group_role=add_group_role)
    if not node.get("children"):
        return node.get("role") in NodeCategory.INTERACTION.roles(add_group_role=False)
    return len(children_roles(node).difference(interaction_roles)) == 0


def group_text_children(node: A11yNode) -> A11yNode:
    if not node.get("children"):
        raise InvalidA11yChildrenError(
            check=f"group_text_children: {node}",
            nb_children=0,
        )

    text_group_children: list[A11yNode] = []
    text_group_roles: set[str] = set()
    other_children: list[A11yNode] = []
    for child in node.get("children", []):
        if is_text_group(child):
            text_group_children.append(child)
            text_group_roles.update(children_roles(child))
        else:
            other_children.append(child)
    if len(text_group_children) == 0:
        raise InvalidA11yChildrenError(
            check=(
                "Text group should have text children roles instead"
                f" of {children_roles(node)}"
                f" for {[children_roles(c) for c in node.get('children', [])]}"
            ),
            nb_children=0,
        )

    def transform_to_markdown(children: list[A11yNode], join_with: str = "\n") -> str:
        if isinstance(children, dict):
            raise InvalidInternalCheckError(
                check=f"Wrong type for children: {children}",
                dev_advice="This should not happen. You should check the code to see why this is happening.",
                url=None,
            )
        markdown = ""
        for child in children:
            if child.get("role") == "heading":
                markdown += f"## {child['name']}{join_with}"
            elif child.get("role") == "text":
                markdown += f"{child['name']}{join_with}"
            elif child.get("role") in ["group", "generic", "none"]:
                markdown += transform_to_markdown(child.get("children", []), "\n *")
        return markdown

    def concat_text(children: list[A11yNode]) -> str:
        def flatten_text(node: A11yNode) -> list[str]:
            if node.get("role") in ["heading", "text"]:
                return [node["name"]]
            if node.get("children"):
                return [text for child in node.get("children", []) for text in flatten_text(child)]
            return []

        flattened_texts = [text for child in children for text in flatten_text(child)]
        if len(flattened_texts) == 0:
            raise InvalidA11yChildrenError(
                check=f"No text children found in {children}",
                nb_children=len(children),
            )

        flattened_texts_distrib = set([len(text) for text in flattened_texts])

        if max(flattened_texts_distrib) <= 3:
            return "".join(flattened_texts)

        # follow up 1 char strings should be concatenated without spaces
        # to avoid having a long text with a lot of spaces

        def group_1_char_strings(texts: list[str]) -> list[str]:
            grouped_texts: list[str] = []
            current_text = ""
            for text in texts:
                if len(text) == 1:
                    current_text += text
                else:
                    if current_text:
                        grouped_texts.append(current_text)
                        current_text = ""
                    grouped_texts.append(text)
            # Don't forget to append the last group if it exists
            if current_text:
                grouped_texts.append(current_text)

            return grouped_texts

        init_flattened_texts_len = len(flattened_texts)
        flattened_texts = group_1_char_strings(flattened_texts)

        if init_flattened_texts_len <= 3:
            # bullet points are more readable than long texts
            return ", ".join(flattened_texts)
        # other wise, flatten by concatenating with spaces
        return " ".join(flattened_texts)

    if "heading" in text_group_roles:
        markdown = transform_to_markdown(text_group_children)
    else:
        markdown = concat_text(text_group_children)

    if len(other_children) == 0:
        if node["name"] != "":
            markdown = f"# {node['name']}\n\n" + markdown
        else:
            node["name"] = markdown
        node = add_group_role(node, "text-group")
        node["markdown"] = markdown
        node["children_roles_count"] = inner_compute_children_roles_count(text_group_children)
        del node["children"]
    else:
        # print("---------------------------------------")
        node["children"] = other_children
        node["children"].append(
            {
                "role": "text",
                "group_role": "text-group",
                # 'name': 'YOYYYYYYYYYYYYYYYYYYYYYYYY',
                "name": "",
                "markdown": markdown,
                "children_roles_count": inner_compute_children_roles_count(other_children),
            }
        )

    return node


def group_interaction_children(node: A11yNode) -> A11yNode:
    if not node.get("children"):
        raise InvalidA11yChildrenError(
            check=f"Group nodes should have children: {node}",
            nb_children=0,
        )
    # flatten all interactions elemnets into a single menu
    interactions_children: list[A11yNode] = []
    other_children: list[A11yNode] = []
    for child in node.get("children", []):
        if is_interaction_group(child):
            interactions_children.append(child)
        else:
            # TODO: FIX THIS OTHERWISE INTERACTION CHILDREN WILL BE REORDERED
            # WHICH WILL CAUSE PROBLEMS WITH THE NOTTE IDS
            if not all([role not in children_roles(child) for role in NodeCategory.INTERACTION.roles()]):
                raise InvalidA11yChildrenError(
                    check=f"Child {child} has invalid roles: {children_roles(child)}",
                    nb_children=len(node.get("children", [])),
                )
            other_children.append(child)
    if len(interactions_children) == 0:
        raise InvalidA11yChildrenError(
            check=(
                "Interaction group should have interaction children roles instead"
                f" of {children_roles(node)}"
                f" for {[children_roles(c) for c in node.get('children', [])]}"
            ),
            nb_children=len(node.get("children", [])),
        )
    # flatten all interactions elemnets into a single menu list

    def flatten_interactions(children: list[A11yNode]) -> list[A11yNode]:
        flattened: list[A11yNode] = []
        for child in children:
            if child.get("role") in NodeCategory.INTERACTION.roles():
                flattened.append(child)
            elif child.get("children") and child.get("role") in [
                "group",
                "generic",
                "none",
            ]:
                flattened.extend(flatten_interactions(child.get("children", [])))
            else:
                sub_children = flatten_interactions(child.get("children", []))
                flattened.append(
                    {
                        "role": child["role"],
                        "group_role": "interaction-group",
                        "name": child["name"],
                        "children": sub_children,
                        "children_roles_count": inner_compute_children_roles_count(sub_children),
                    }
                )
        return flattened

    flattened_interactions = flatten_interactions(interactions_children)
    nb_interactions = sum(
        [
            child.get("children_roles_count", {}).get(interaction_role, 0)
            for child in flattened_interactions
            for interaction_role in NodeCategory.INTERACTION.roles()
        ]
    )
    if nb_interactions < 2:
        raise InvalidA11yChildrenError(
            check=f"Interactions should have at least 2 children: {flattened_interactions}",
            nb_children=len(flattened_interactions),
        )

    if len(other_children) == 0:
        node = add_group_role(node, "interaction-group")
        node["children"] = flattened_interactions
        node["children_roles_count"] = inner_compute_children_roles_count(flattened_interactions)
    else:
        # print("---------------------------------------")
        node["children"] = other_children
        node["children"].append(
            {
                "role": "group",
                "group_role": "interaction-group",
                # 'name': 'KKKAKKAKAKAKAKAKKAKAKAKKAKA',
                "name": "",
                "children": flattened_interactions,
                "children_roles_count": inner_compute_children_roles_count(flattened_interactions),
            }
        )
    return node


def group_table_children(node: A11yNode) -> A11yNode:
    logger.error(f"Table grouping is not implemented yet for node {node}")
    return node


def group_list_text_children(node: A11yNode) -> A11yNode:
    if not node.get("children"):
        raise InvalidA11yChildrenError(
            check=f"Group nodes should have children: {node}",
            nb_children=0,
        )

    def transform_to_markdown_list(children: list[A11yNode], level: int = 0) -> str:
        markdown = ""
        indent = "  " * level

        for child in children:
            # Skip ListMarker nodes
            if child.get("role") == "ListMarker":
                continue

            if child.get("role") == "listitem":
                # Get text content from listitem's children
                text_content = ""
                for subchild in child.get("children", []):
                    if subchild.get("role") == "text":
                        text_content = subchild.get("name", "").strip()
                        break

                if text_content:
                    markdown += f"{indent}* {text_content}\n"

                # Handle nested lists
                nested_items = [c for c in child.get("children", []) if c.get("role") in ["list", "listitem"]]
                if nested_items:
                    markdown += transform_to_markdown_list(nested_items, level + 1)

            elif child.get("role") == "list":
                markdown += transform_to_markdown_list(child.get("children", []), level)

            elif child.get("role") == "text":
                text = child.get("name", "").strip()
                if text:
                    markdown += f"{indent}{text}\n"

        return markdown

    markdown = transform_to_markdown_list(node.get("children", []))

    # Create new node with markdown content
    if node["role"] != "list":
        raise InvalidA11yChildrenError(
            check=f"List text group should have list role instead of {node['role']}",
            nb_children=len(node.get("children", [])),
        )
    if node["name"]:
        markdown = f"# {node['name']}\n\n{markdown}"

    new_node: A11yNode = {
        "role": "text",
        "name": "",
        "group_role": "list-text-group",
        "markdown": markdown.strip(),
        "children_roles_count": {"text": 1},
    }

    return new_node


def prune_non_interaction_node(node: A11yNode, append_text_node: bool = False) -> A11yNode:
    # Heuristic:
    # If current node has some children that are interactions
    # Then the other children that don't have interaction role
    # are candidates to be pruned
    # => e.g. text elements, list items, etc.

    children = node.get("children", [])
    if not children:
        return node

    interactions_children: list[A11yNode] = []
    other_children: list[A11yNode] = []

    interaction_roles = NodeCategory.INTERACTION.roles()
    for child in children:
        child_roles = children_roles(child)
        child_roles.add(child["role"])

        if child_roles.intersection(interaction_roles):
            interactions_children.append(child)
        else:
            other_children.append(child)

    if len(other_children) <= 0:
        return node

    # replace all other_children with a placeholder text node

    print(
        f"Prune nb_other_children: {len(other_children)} with roles {inner_compute_children_roles_count(other_children)}"
    )

    node["children"] = interactions_children
    if append_text_node:
        node["children"].append(
            {
                "role": "text",
                "name": "pruned text ...",
                "group_role": "pruned-group",
                "children_roles_count": {"text": 1},
            }
        )
    return node


def group_a11y_node(
    node: A11yNode,
    group_types: list[NodeCategory] | None = None,
    prune_non_interaction: bool = True,  # type: ignore[unused-argument]
) -> A11yNode:
    node = compute_children_roles(node)

    _group_types = group_types if group_types else [NodeCategory.TEXT]
    for group_type in _group_types:
        if should_group(node, group_type.roles(), add_group_role=True):
            node = get_group_func(group_type)(node)

    # if prune_non_interaction:
    #     node = prune_non_interaction_node(node)

    return node


def group_following_text_nodes(node: A11yNode) -> A11yNode:
    children = node.get("children")
    if children is None:
        return node
    following_text_nodes: list[str] = []
    new_children: list[A11yNode] = []

    def add_nodes(nodes: list[str]) -> None:
        if len(nodes) > 0:
            new_children.append(
                {
                    "role": "text",
                    "name": " ".join(following_text_nodes),
                }
            )

    for _child in children:
        child = group_following_text_nodes(_child)
        match (node["role"], child["role"]):
            case ("list", "text"):
                # list items are not grouped
                # otherwise we lose structural information, e.g.
                # list {
                #     text "Advanced dual-camera system"
                #     text "48MP Fusion camera"
                #     text "2x Telephoto"
                #     text "12MP Ultra Wide camera"
                # }
                new_children.append(child)
            case (_, "text"):
                following_text_nodes.append(child["name"])
            case (_, "LineBreak"):
                following_text_nodes.append("\n")
            # case "heading":
            #     following_text_nodes.append(f"# {child['name']} \n")
            case _:
                add_nodes(following_text_nodes)
                following_text_nodes = []
                new_children.append(child)
    add_nodes(following_text_nodes)
    node["children"] = new_children
    return node
