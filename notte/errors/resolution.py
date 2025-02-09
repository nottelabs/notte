from notte.browser.dom_tree import DomNode, NodeSelectors
from notte.errors.processing import InvalidInternalCheckError


class NodeResolutionAttributeError(InvalidInternalCheckError):
    def __init__(self, node: DomNode, error_component: str) -> None:
        super().__init__(
            check=f"node '{error_component}' are required to create an executable action from a node but are None",
            url=node.get_url(),
            dev_advice=(
                "This technnically should never happen. There is likely an issue during node resolution "
                "pipeline, i.e `notte.pipe.resolution.py:compute_attributes`."
            ),
        )


class FailedSimpleNodeResolutionError(InvalidInternalCheckError):
    def __init__(self, node_id: str):
        super().__init__(
            check=f"No selector found for action {node_id}",
            url=None,
            dev_advice=(
                "This technnically should never happen. There is likely an issue during playright "
                "conflict resolution pipeline, i.e `SimpleActionResolutionPipe`."
            ),
        )


class FailedNodeResolutionError(InvalidInternalCheckError):
    def __init__(self, node: DomNode) -> None:
        super().__init__(
            check=(
                f"Failed to resolve playwright locator for node (id='{node.id}', role='{node.role}', "
                f"text='{node.text}')"
            ),
            url=node.get_url(),
            dev_advice=(
                "This technnically should never happen. There is likely an issue during node resolution "
                "pipeline, i.e `notte.pipe.resolution.py:compute_attributes`."
            ),
        )


class ConflictResolutionCheckError(InvalidInternalCheckError):
    def __init__(self, check: str) -> None:
        super().__init__(
            check=check,
            url=None,
            dev_advice=(
                "This technnically should never happen. There is likely an issue during playright "
                "conflict resolution pipeline, i.e `notte.pipe.preprocessing.a11y.conflict_resolution.py`."
            ),
        )


class FailedUniqueLocatorResolutionError(InvalidInternalCheckError):
    def __init__(self, selectors: NodeSelectors) -> None:
        super().__init__(
            check=f"Failed to resolve unique playwright locator for selectors: {selectors.selectors()}",
            url=None,
            dev_advice=(
                "This technnically should never happen. There is likely an issue during playright "
                "conflict resolution pipeline, i.e `notte.pipe.preprocessing.a11y.conflict_resolution.py`."
            ),
        )
