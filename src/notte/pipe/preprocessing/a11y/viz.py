from typing import Literal

from notte.browser.dom_tree import A11yNode


def a11tree_to_tree_string(
    node: A11yNode,
    prefix: str = "",
    is_last: bool = True,
) -> str:
    # Start with the current node
    result = prefix + ("└── " if is_last else "├── ")

    # Add node content
    group_role_str = "" if "group_role" not in node else f" as {node['group_role']}"
    notte_id_str = "" if "id" not in node else f" ({node['id']})"
    node_text = f"[{node['role']}{group_role_str}] '{node.get('name', '')}' {notte_id_str}"
    if node.get("selected"):
        node_text += " (selected)"
    result += node_text + "\n"

    if "markdown" in node:
        new_prefix = prefix + ("    " if is_last else "│   ")
        m: str = node["markdown"]
        ellips = (m[:40] + "...") if len(m) > 40 else m
        result += new_prefix + f"    {ellips}\n"
        return result

    # Handle children
    if "children" in node and node["children"]:
        children = node["children"]
        for i, child in enumerate(children):
            is_last_child = i == len(children) - 1
            # Add proper prefix for child levels
            new_prefix = prefix + ("    " if is_last else "│   ")
            result += a11tree_to_tree_string(child, new_prefix, is_last_child)

    return result


def a11tree_to_markdown(node: A11yNode, heading_level: int = 1) -> str:
    markdown = ""
    role, name = node.get("role", "").strip(), node.get("name", "").strip()
    notte_id_str = f" ({node['id']})" if "id" in node else ""
    # Handle different node types
    if role == "link":
        link_text = name
        link_href = "none"
        # TODO: add this back once we figure out how to get the href
        # link_href = node.get("attributes", {}).get("href", "#")

        markdown += f"[{link_text}]({link_href}){notte_id_str}\n"

    elif role == "button":
        markdown += f"Button:{name}{notte_id_str}\n"

    elif role == "list":
        markdown += "\n"  # Add spacing before list
        for child in node.get("children", []):
            markdown += f"* {a11tree_to_markdown(child, heading_level).strip()}\n"
        markdown += "\n"

    elif role == "listitem":
        # Process contents of list item without bullet
        for child in node.get("children", []):
            markdown += a11tree_to_markdown(child, heading_level)

    elif role == "text" and name:
        markdown += f"{name} "

    elif role not in ["", "none", "group"] and (len(name) > 1 or (len(name) == 1 and name.isalnum())):
        last_line = markdown.split("\n")[-1]
        if not last_line.startswith("#") and not markdown.endswith("\n\n"):
            markdown += "\n"
        markdown += f"{'#' * heading_level} {name}{notte_id_str}\n"
        for child in node.get("children", []):
            markdown += a11tree_to_markdown(child, heading_level + 1)

    else:
        if name:
            markdown += f"{name}{notte_id_str}\n"

        for child in node.get("children", []):
            markdown += a11tree_to_markdown(child, heading_level)
        # markdown += "\n"

    return markdown


def visualize_a11y_tree(
    root_node: A11yNode,
    output_format: Literal["tree", "markdown", "..."] = "tree",
) -> str:
    match output_format:
        case "tree":
            # Start with root node without prefix
            root_text = f"[{root_node['role']}] '{root_node.get('name', '')}'\n"

            # Add children
            if "children" in root_node and root_node["children"]:
                for i, child in enumerate(root_node["children"]):
                    is_last = i == len(root_node["children"]) - 1
                    root_text += a11tree_to_tree_string(
                        node=child,
                        prefix="",
                        is_last=is_last,
                    )
        case "markdown":
            root_text = a11tree_to_markdown(root_node)
        case _:
            raise ValueError(f"Invalid output format: {output_format}")

    return root_text
