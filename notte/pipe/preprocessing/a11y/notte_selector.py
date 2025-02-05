from notte.browser.dom_tree import A11yNode
from notte.pipe.preprocessing.a11y.id_generation import as_dict


def generate_notte_selector(node: A11yNode, notte_selector: str = "") -> A11yNode:
    _node = as_dict(node)
    node_path = ":".join([notte_selector, _node["role"], _node["name"]])
    node["path"] = node_path
    for child in _node.get("children", []):
        _ = generate_notte_selector(child, node_path)
    return node
