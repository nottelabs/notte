from notte.browser.node_type import A11yNode
from notte.errors.processing import InvalidInternalCheckError


def children_roles(a11y_node: A11yNode) -> set[str]:
    roles = a11y_node.get("children_roles_count")
    if not roles:
        return set()
    return set(roles.keys())


def add_group_role(node: A11yNode, group_role: str) -> A11yNode:
    if not node.get("group_role"):
        if node.get("group_roles"):
            raise InvalidInternalCheckError(
                check=f"Group role should not be set if group_roles is not set: {node}",
                dev_advice=(
                    "This is an assumption that should not be violated."
                    " However this code has been created a long time ago and may need to be revisited."
                ),
                url=None,
            )
        node["group_role"] = group_role
        node["group_roles"] = []
    else:
        node["group_roles"].append(node["group_role"])
        node["group_role"] = group_role
    return node


def compute_children_roles_count(node: A11yNode) -> A11yNode:
    node["children_roles_count"] = _compute_children_roles_count(children=node.get("children", []))
    return node


def _compute_children_roles_count(children: list[A11yNode]) -> dict[str, int]:
    children_roles_count = {}

    def increment_role(role: str, count: int) -> None:
        if role not in children_roles_count:
            children_roles_count[role] = 0
        children_roles_count[role] += count

    for child in children:
        # add curenent role because it's not part of the its children_roles_count
        # but should be part of the parent's children_roles_count
        increment_role(child["role"], 1)
        child_count = child.get("children_roles_count")
        if not child_count:
            # simply define it so that `children_roles_count` always exists
            # no need to add the current role because it was already added
            # by the previous increment_role call
            child["children_roles_count"] = {child["role"]: 1}
        else:
            for role, count in child_count.items():
                increment_role(role, count)
    return children_roles_count


def compute_children_roles(node: A11yNode) -> A11yNode:
    return compute_children_roles_count(node)
