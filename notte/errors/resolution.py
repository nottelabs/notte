from notte.browser.node_type import NotteNode
from notte.errors.processing import InvalidInternalCheckError


class NodeResolutionAttributeError(InvalidInternalCheckError):
    def __init__(self, node: NotteNode, error_component: str) -> None:
        super().__init__(
            check=(
                (f"node '{error_component}' are required to create an executable action from a node " "but are None")
            ),
            url=node.get_url(),
            dev_advice=(
                (
                    "This technnically should never happen. There is likely an issue during node resolution "
                    "pipeline, i.e `notte.pipe.resolution.py:compute_attributes`."
                )
            ),
        )


class FailedNodeResolutionError(InvalidInternalCheckError):
    def __init__(self, node: NotteNode) -> None:
        super().__init__(
            check=(
                (
                    f"Failed to resolve playwright locator for node (id='{node.id}', role='{node.role}', "
                    f"text='{node.text}')"
                )
            ),
            url=node.get_url(),
            dev_advice=(
                (
                    "This technnically should never happen. There is likely an issue during node resolution "
                    "pipeline, i.e `notte.pipe.resolution.py:compute_attributes`."
                )
            ),
        )


class ConflictResolutionCheckError(InvalidInternalCheckError):
    def __init__(self, check: str) -> None:
        super().__init__(
            check=check,
            url=None,
            dev_advice=(
                (
                    "This technnically should never happen. There is likely an issue during playright "
                    "conflict resolution pipeline, i.e `notte.pipe.preprocessing.a11y.conflict_resolution.py`."
                )
            ),
        )
