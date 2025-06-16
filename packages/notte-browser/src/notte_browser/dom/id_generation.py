from collections import defaultdict

from loguru import logger
from notte_core.browser.node_type import NodeRole
from notte_core.profiling import profiler

from notte_browser.dom.types import DOMBaseNode


@profiler.profiled()
def generate_sequential_ids(root: DOMBaseNode) -> DOMBaseNode:
    """
    Generates sequential IDs for interactive elements in the accessibility tree
    using depth-first search.
    """
    stack = [root]
    id_counter: defaultdict[str, int] = defaultdict(lambda: 1)
    while stack:
        node = stack.pop()
        children = node.children

        role = NodeRole.from_value(node.role)
        if isinstance(role, str):
            logger.debug(
                f"Unsupported role to convert to ID: {node}. Please add this role to the NodeRole e logic ASAP."
            )
        elif node.highlight_index is not None:
            id = role.short_id(force_id=True)
            if id is not None:
                node.notte_id = f"{id}{id_counter[id]}"
                id_counter[id] += 1
            else:
                raise ValueError(
                    (
                        f"Role {role} was incorrectly converted from raw Dom Node."
                        " It is an interaction node. It should have a short ID but is currently None"
                    )
                )
        stack.extend(reversed(children))

    return root
