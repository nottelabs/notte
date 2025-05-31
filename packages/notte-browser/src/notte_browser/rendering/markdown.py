from loguru import logger
from notte_core.browser.dom_tree import DomNode


class MarkdownDomNodeRenderingPipe:
    @staticmethod
    def forward(
        node: DomNode,
        include_ids: bool,
        verbose: bool = False,
    ) -> str:
        if verbose:
            logger.trace(f"Dom Node markdown rendering with include_ids={include_ids}")
        return MarkdownDomNodeRenderingPipe.format(
            node,
            indent_level=0,
            include_ids=include_ids,
            expand_non_interaction_subtree=False,
        )

    @staticmethod
    def format(
        node: DomNode,
        indent_level: int = 0,
        include_ids: bool = True,
        expand_non_interaction_subtree: bool = False,
    ) -> str:
        indent = " " * indent_level

        # Start with role and optional text
        id_str = ""
        if node.id is not None and include_ids:
            id_str = f" {node.id}"

        result = f"{indent}{node.get_role_str()}{id_str}"
        if len(node.text.strip()) > 0:
            result += f' "{node.text}"'

        # iterate dom attributes
        if node.attributes is not None:
            dom_attrs = [
                f"{key}={value}"
                for key, value in node.attributes.relevant_attrs().items()
                if str(value) not in node.text
            ]

            if dom_attrs:
                # TODO: prompt engineering to select the most readable format
                # for the LLM to understand this information
                result += " " + " ".join(dom_attrs)

        # Recursively format children
        if len(node.children) > 0:
            result += " {\n"
            for child in node.children:
                if len(child.subtree_ids) == 0 and not expand_non_interaction_subtree:
                    inner_text = child.inner_text().strip()
                    if len(inner_text) > 0:
                        result += f"{indent} inner_text: {inner_text}\n"
                else:
                    result += MarkdownDomNodeRenderingPipe.format(
                        child,
                        indent_level + 1,
                        include_ids=include_ids,
                        expand_non_interaction_subtree=expand_non_interaction_subtree,
                    )
            result += indent + "}\n"
        else:
            result += "\n"

        return result
