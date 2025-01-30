from notte.browser.dom_tree import DomNode


class InteractionOnlyDomNodeRenderingPipe:
    @staticmethod
    def format(
        node: DomNode,
        depth: int,
        node_texts: list[str],
        include_attributes: list[str],
        is_parent_interaction: bool = False,
    ) -> list[str]:
        if node.get_role_str() == "text":
            # Add text only if it doesn't have a highlighted parent
            if not is_parent_interaction:
                node_texts.append(f"_[:]{node.text}")
        else:
            is_parent_interaction = False
            # Add element with highlight_index
            if node.id is not None:
                is_parent_interaction = True
                attrs = node.attributes
                attrs_str = ""
                tag_name = ""
                if include_attributes and attrs is not None:
                    tag_name = attrs.tag_name
                    attrs_str = " " + " ".join(
                        f'{key}="{value}"' for key, value in attrs.relevant_attrs().items() if key in include_attributes
                    )
                children_texts = InteractionOnlyDomNodeRenderingPipe.children_texts(node)
                children_str = "\n".join(children_texts).strip()
                node_texts.append(f"{node.id}[:]<{tag_name}{attrs_str}>{children_str}</{tag_name}>")

            # Process children regardless
            for child in node.children:
                node_texts = InteractionOnlyDomNodeRenderingPipe.format(
                    node=child,
                    depth=depth + 1,
                    node_texts=node_texts,
                    include_attributes=include_attributes,
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

            if node.get_role_str() == "text":
                texts.append(node.text)
            else:
                for child in node.children:
                    collect_text(child, current_depth + 1)

        collect_text(root_node, 0)
        return texts

    @staticmethod
    def forward(node: DomNode, include_attributes: list[str] | None = None) -> str:
        """Convert the processed DOM content to HTML."""

        formatted_text: list[str] = InteractionOnlyDomNodeRenderingPipe.format(
            node=node,
            depth=0,
            node_texts=[],
            include_attributes=include_attributes or [],
        )
        return "\n".join(formatted_text)
