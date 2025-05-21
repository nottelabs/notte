from collections.abc import Sequence

from notte_core.actions.base import ActionParameterValue, ExecutableAction
from notte_core.browser.dom_tree import DomNode, InteractionDomNode
from notte_core.browser.snapshot import BrowserSnapshot
from notte_core.controller.actions import BaseAction
from notte_core.controller.space import ActionSpace
from notte_core.errors.processing import InvalidInternalCheckError
from notte_sdk.types import PaginationParams
from typing_extensions import override

from notte_browser.rendering.interaction_only import InteractionOnlyDomNodeRenderingPipe
from notte_browser.rendering.pipe import (
    DomNodeRenderingPipe,
    DomNodeRenderingType,
)
from notte_browser.tagging.action.base import BaseActionSpacePipe


class SimpleActionSpacePipe(BaseActionSpacePipe):
    def node_to_executable(self, node: InteractionDomNode) -> ExecutableAction:
        selectors = node.computed_attributes.selectors
        if selectors is None:
            raise InvalidInternalCheckError(
                check="Node should have an xpath selector",
                url=node.get_url(),
                dev_advice="This should never happen.",
            )
        return ExecutableAction(
            id=node.id,
            category="Interaction action",
            description=InteractionOnlyDomNodeRenderingPipe.render_node(node),
            node=node,
            params_values=[
                ActionParameterValue(
                    name="value",
                    value="<sample_value>",
                )
            ],
        )

    def actions(self, node: DomNode) -> list[BaseAction]:
        return [self.node_to_executable(inode) for inode in node.interaction_nodes()]

    @override
    def forward(
        self,
        snapshot: BrowserSnapshot,
        previous_action_list: Sequence[BaseAction] | None,
        pagination: PaginationParams,
    ) -> ActionSpace:
        page_content = DomNodeRenderingPipe.forward(snapshot.dom_node, type=DomNodeRenderingType.INTERACTION_ONLY)
        return ActionSpace(
            description=page_content,
            raw_actions=self.actions(snapshot.dom_node),
        )
