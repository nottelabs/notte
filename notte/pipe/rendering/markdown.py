from notte.browser.dom_tree import DomNode
from notte.browser.node_type import NodeCategory


class MarkdownDomNodeRenderingPipe:
    @staticmethod
    def forward(
        node: DomNode,
        include_ids: bool,
        include_images: bool,
    ) -> str:
        return MarkdownDomNodeRenderingPipe.format(
            node,
            indent_level=0,
            include_ids=include_ids,
            include_images=include_images,
        )

    @staticmethod
    def format(
        node: DomNode,
        indent_level: int = 0,
        include_ids: bool = True,
        include_images: bool = False,
    ) -> str:
        indent = "  " * indent_level

        # Start with role and optional text
        result = f"{indent}{node.get_role_str()}"
        if node.text is not None and node.text != "":
            result += f' "{node.text}"'

        # Add attributes
        attrs: list[str] = []
        if node.id is not None and (
            include_ids or (include_images and node.get_role_str() in NodeCategory.IMAGE.roles())
        ):
            attrs.append(node.id)

        # iterate pre-over attributes
        if node.attributes is not None:
            attrs = [f"{key}={value}" for key, value in node.attributes.relevant_attrs().items()]
            attrs.extend(attrs)

        if attrs:
            # TODO: prompt engineering to select the most readable format
            # for the LLM to understand this information
            result += " " + " ".join(attrs)

        # Recursively format children
        if len(node.children) > 0:
            result += " {\n"
            for child in node.children:
                result += MarkdownDomNodeRenderingPipe.format(
                    child, indent_level + 1, include_ids=include_ids, include_images=include_images
                )
            result += indent + "}\n"
        else:
            result += "\n"

        return result
