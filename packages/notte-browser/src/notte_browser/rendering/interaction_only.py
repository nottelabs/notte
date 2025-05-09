from loguru import logger
from notte_core.browser.dom_tree import DomNode
from notte_core.browser.node_type import NodeType
from notte_core.errors.processing import InvalidInternalCheckError


class InteractionOnlyDomNodeRenderingPipe:
    @staticmethod
    def render_node(
        node: DomNode,
        include_attributes: frozenset[str] | None = None,
        max_len_per_attribute: int | None = None,
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
        attrs_relevant = attrs.relevant_attrs(include_attributes, max_len_per_attribute)
        if len(attrs_relevant) > 0:
            attrs_str = " " + " ".join([f'{key}="{value}"' for key, value in attrs_relevant.items()])
        children_texts = InteractionOnlyDomNodeRenderingPipe.children_texts(node)
        children_str = "\n".join(children_texts).strip()
        return f"<{attrs.tag_name}{attrs_str}>{children_str}</{attrs.tag_name}>"

    @staticmethod
    def format(
        node: DomNode,
        depth: int,
        node_texts: list[str],
        include_attributes: frozenset[str] | None,
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
                html_description = InteractionOnlyDomNodeRenderingPipe.render_node(
                    node, include_attributes, max_len_per_attribute
                )
                node_texts.append(f"{node.id}[:]{html_description}")

            # Process children regardless
            for child in node.children:
                _ = InteractionOnlyDomNodeRenderingPipe.format(
                    node=child,
                    depth=depth + 1,
                    node_texts=node_texts,
                    include_attributes=include_attributes,
                    max_len_per_attribute=max_len_per_attribute,
                    is_parent_interaction=is_parent_interaction,
                )
        return node_texts

    @staticmethod
    def children_texts(root_node: DomNode, max_depth: int = -1) -> list[str]:
        texts: list[str] = []

        def collect_text(node: DomNode, current_depth: int) -> None:
            if max_depth != -1 and current_depth > max_depth:
                return

            # Skip this branch if we hit a highlighted element (except for the current node)
            if node.id is not None and node.id != root_node.id:
                return

            if node.get_role_str() == "text" and len(node.text.strip()) > 0:
                texts.append(node.text.strip())
            else:
                for child in node.children:
                    collect_text(child, current_depth + 1)

        collect_text(root_node, 0)
        return texts

    @staticmethod
    def forward(
        node: DomNode,
        include_attributes: frozenset[str] | None = None,
        max_len_per_attribute: int | None = None,
        verbose: bool = False,
    ) -> str:
        """Convert the processed DOM content to HTML."""
        # inodes = "\n".join([str(inode) for inode in node.interaction_nodes()])
        # logger.info(f"📄 Rendering interaction only node: \n{inodes}")
        component_node_strs: list[str] = []
        components = node.prune_non_dialogs_if_present()

        for component_node in components:
            formatted_text: list[str] = InteractionOnlyDomNodeRenderingPipe.format(
                node=component_node,
                depth=0,
                node_texts=[],
                include_attributes=include_attributes,
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
            logger.info(f"📄 Rendered node: \n{rendered_node}")
        return rendered_node
