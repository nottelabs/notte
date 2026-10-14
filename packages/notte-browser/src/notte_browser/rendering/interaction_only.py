from notte_core.browser.dom_tree import DomNode
from notte_core.browser.node_type import NodeType
from notte_core.common.logging import logger
from notte_core.errors.processing import InvalidInternalCheckError

INCLUDE_ATTRIBUTES: frozenset[str] = frozenset(
    [
        "title",
        "type",
        "name",
        "role",
        "tabindex",
        "aria_label",
        "placeholder",
        "value",
        "alt",
        "src",
        "href",
        "aria_expanded",
    ]
)


def render_node(
    node: DomNode,
    max_len_per_attribute: int | None = None,
    *,
    include_children: bool = True,
) -> str:
    if node.id is None:
        raise InvalidInternalCheckError(
            check="Node should have an id",
            url=node.get_url(),
            dev_advice="This should never happen.",
        )
    attrs = node.attributes
    if attrs is None:
        raise ValueError(f"Attributes are None for node: {node}")
    attrs_str = ""
    attrs_relevant = attrs.relevant_attrs(
        include_attributes=INCLUDE_ATTRIBUTES,
        max_len_per_attribute=max_len_per_attribute,
    )
    if len(attrs_relevant) > 0:
        attrs_str = " " + " ".join([f'{key}="{value}"' for key, value in attrs_relevant.items()])
    if include_children:
        children_str = "\n".join(children_texts(node)).strip()
    else:
        # Action descriptions used childless copies with text=inner_text(), without attribute truncation.
        children_str = node.inner_text().strip() if node.get_role_str() == "text" else ""
    return f"<{attrs.tag_name}{attrs_str}>{children_str}</{attrs.tag_name}>"


def format_node(
    node: DomNode,
    node_texts: list[str],
    max_len_per_attribute: int | None,
    is_parent_interaction: bool = False,
) -> list[str]:
    if node.type.value == NodeType.TEXT.value:
        if len(node.children) > 0:
            raise InvalidInternalCheckError(
                check="Text node should not have children",
                url=node.get_url(),
                dev_advice="This should never happen.",
            )
        # Add text only if it doesn't have a highlighted parent
        if not is_parent_interaction and len(node.text.strip()) > 0:
            node_texts.append(f"_[:]{node.text.strip()}")
    else:
        # Add element with highlight_index
        if node.id is not None:
            is_parent_interaction = True
            html_description = render_node(node, max_len_per_attribute)
            node_texts.append(f"{node.id}[:]{html_description}")

        # Process children regardless
        for child in node.children:
            _ = format_node(
                node=child,
                node_texts=node_texts,
                max_len_per_attribute=max_len_per_attribute,
                is_parent_interaction=is_parent_interaction,
            )
    return node_texts


def children_texts(root_node: DomNode) -> list[str]:
    texts: list[str] = []

    def collect_text(node: DomNode) -> None:
        # Skip this branch if we hit a highlighted element (except for the current node)
        if node.id is not None and node.id != root_node.id:
            return

        if node.get_role_str() == "text" and len(node.text.strip()) > 0:
            texts.append(node.text.strip())
        else:
            for child in node.children:
                collect_text(child)

    collect_text(root_node)
    return texts


def render_interactions(
    node: DomNode,
    max_len_per_attribute: int | None = None,
    verbose: bool = False,
) -> str:
    """Convert the processed DOM content to HTML."""
    component_node_strs: list[str] = []
    components = node.prune_non_dialogs_if_present()
    for component_node in components:
        formatted_text: list[str] = format_node(
            node=component_node,
            node_texts=[],
            max_len_per_attribute=max_len_per_attribute,
        )

        rendered_component = "\n".join(formatted_text).strip()
        if len(components) > 0:
            # more than 1 component => modals here add some special text to separate them
            rendered_component = f"""
### Content of '{component_node.get_role_str()}' component with text '{component_node.text}'
{rendered_component}
"""
        component_node_strs.append(rendered_component)

    rendered_node = "\n".join(component_node_strs).strip()
    if verbose:
        logger.trace(f"📄 Rendered node: \n{rendered_node}")
    return rendered_node
