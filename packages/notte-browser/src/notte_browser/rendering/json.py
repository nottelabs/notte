import json

from loguru import logger
from notte_core.browser.dom_tree import A11yNode, DomNode


class JsonDomNodeRenderingPipe:
    @staticmethod
    def _dom_node_to_dict(
        node: DomNode,
        include_ids: bool,
        include_links: bool,
    ) -> A11yNode:
        _dict: A11yNode = {
            "role": node.get_role_str(),
            "name": node.text,
        }
        if include_ids and node.id is not None:
            _dict["id"] = node.id
        attrs = node.attributes
        if attrs is not None:
            relevant_attrs = attrs.relevant_attrs()
            if not include_links and "href" in relevant_attrs:
                del relevant_attrs["href"]
            _dict.update(relevant_attrs)  # type: ignore[arg-type]
        # add children
        if len(node.children) > 0:
            _dict["children"] = [
                JsonDomNodeRenderingPipe._dom_node_to_dict(child, include_ids, include_links) for child in node.children
            ]
        return _dict

    @staticmethod
    def forward(
        node: DomNode,
        include_ids: bool = True,
        include_links: bool = False,
        verbose: bool = False,
    ) -> str:
        dict_node = JsonDomNodeRenderingPipe._dom_node_to_dict(
            node,
            include_ids=include_ids,
            include_links=include_links,
        )
        if verbose:
            logger.trace(f"🔍 JSON rendering:\n{dict_node}")
        return json.dumps(dict_node)
