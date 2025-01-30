from notte.browser.dom.views import DOMBaseNode
from notte.browser.dom_tree import A11yNode
from notte.pipe.preprocessing.a11y.id_generation import as_dict


def set_path(node: A11yNode | DOMBaseNode, notte_selector: str) -> None:
    if isinstance(node, dict):
        node["path"] = notte_selector
    else:
        node.notte_selector = notte_selector


def generate_notte_selector(node: A11yNode | DOMBaseNode, notte_selector: str = "") -> A11yNode | DOMBaseNode:
    _node = as_dict(node)
    node_path = ":".join([notte_selector, _node["role"], _node["name"]])
    set_path(node, node_path)
    for child in _node.get("children", []):
        _ = generate_notte_selector(child, node_path)
    return node
