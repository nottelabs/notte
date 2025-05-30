from loguru import logger
from notte_core.browser.dom_tree import DomNode
from notte_core.browser.node_type import NodeCategory, NodeType


def prune_empty_texts(node: DomNode) -> bool:
    if node.type.value == NodeType.TEXT.value:
        if node.text.strip() == "":
            return False
    return True


def prioritize_role(parent: DomNode, child: DomNode) -> str:
    low_priority_roles = ["none", "generic", "group"]
    node_role = parent.get_role_str()
    child_role = child.get_role_str()
    if node_role == child_role:
        return node_role
    match (node_role in low_priority_roles, child_role in low_priority_roles):
        case (True, True):
            return "group"
        case (True, False):
            return child_role
        case (False, True):
            return node_role
        case (False, False):
            if node_role in ["listitem", "paragraph", "main"]:
                return child_role
            if child_role in ["list", "paragraph"]:
                return node_role
            # always prioritize links, buttons and text (i.e interactive elements)
            if child.id is not None:
                return child_role
            if parent.id is not None:
                return node_role
            return child_role


def prioritize_text(parent: DomNode, child: DomNode) -> str:
    ptext, ctext = parent.text.strip(), child.text.strip()
    if len(ptext) == 0:
        return ctext
    if len(ctext) == 0:
        return ptext
    if ctext in ptext:
        # child text is part of parent text => return parent text
        return ptext
    if ptext in ctext:
        # parent text is part of child text => return child text
        return ctext
    # otherwise return concat of both texts
    return ptext + " " + ctext


def _fold_single_child(parent: DomNode, child: DomNode) -> DomNode:
    new_role = prioritize_role(parent, child)
    new_text = prioritize_text(parent, child)

    def build_node(child_priority: bool) -> DomNode:
        return DomNode(
            id=child.id if child_priority else parent.id,
            role=new_role,
            text=new_text,
            # skip parent children since there is only one child
            children=child.children,
            attributes=child.attributes if child_priority else parent.attributes,
            computed_attributes=child.computed_attributes if child_priority else parent.computed_attributes,
            type=child.type if child_priority else parent.type,
        )

    match (parent.id, child.id):
        case (None, None):
            if (child.get_role_str() in NodeCategory.LIST.roles()) or (
                child.get_role_str() in NodeCategory.STRUCTURAL.roles()
            ):
                # skip list/structure child node
                return build_node(child_priority=False)
            # otherwise skip parent node
            return build_node(child_priority=True)
        case (None, _):
            # do not fold if parent has no id
            return build_node(child_priority=True)
        case (_, None):
            # do not fold if child has no id
            return build_node(child_priority=False)
        case (_, _):
            # do not fold if both parent and child have an id
            # TODO: consider cases such as link => button, button => link, etc.
            return parent


def fold_single_childs(node: DomNode) -> DomNode:
    if len(node.children) == 0:
        return node
    pruned_children = [fold_single_childs(child) for child in node.children]
    if len(pruned_children) == 1:
        return _fold_single_child(node, pruned_children[0])
    return DomNode(
        id=node.id,
        role=node.role,
        text=node.text,
        type=node.type,
        children=pruned_children,
        attributes=node.attributes,
        computed_attributes=node.computed_attributes,
    )


def prune_hidden_nodes(node: DomNode) -> bool:
    if node.attributes is None:
        return True
    if node.attributes.hidden or node.attributes.aria_hidden or node.attributes.type == "hidden":
        return False
    return True


def prune_dom_tree(node: DomNode) -> DomNode:
    fnode = node.subtree_filter(lambda n: prune_empty_texts(n))
    # fnode = node.subtree_filter(lambda n: prune_empty_texts(n) and prune_hidden_nodes(n))
    if fnode is None:
        logger.debug("No node found after pruning empty texts")
        fnode = node
    fnode = fold_single_childs(fnode)
    return fnode
