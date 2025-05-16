from collections.abc import Sequence

from notte_core.actions import ActionParameter, InteractionAction
from notte_core.browser.dom_tree import DomNode, InteractionDomNode
from notte_core.browser.snapshot import BrowserSnapshot
from notte_core.errors.processing import InvalidInternalCheckError
from notte_core.space import ActionSpace
from notte_sdk.types import PaginationParams
from typing_extensions import override

from notte_browser.rendering.interaction_only import InteractionOnlyDomNodeRenderingPipe
from notte_browser.rendering.pipe import (
    DomNodeRenderingPipe,
    DomNodeRenderingType,
)
from notte_browser.tagging.action.base import BaseActionSpacePipe
from notte_browser.tagging.type import PossibleAction


class SimpleActionSpacePipe(BaseActionSpacePipe):
    def node_to_interaction(self, node: InteractionDomNode) -> InteractionAction:
        selectors = node.computed_attributes.selectors
        if selectors is None:
            raise InvalidInternalCheckError(
                check="Node should have an xpath selector",
                url=node.get_url(),
                dev_advice="This should never happen.",
            )
        action_description = InteractionOnlyDomNodeRenderingPipe.render_node(node)
        action = PossibleAction(
            id=node.id,
            category="Interaction action",
            description=action_description,
            param=ActionParameter(name="param", type="string") if node.id.startswith("I") else None,
        )
        return action.to_interaction(node)

    def actions(self, node: DomNode) -> list[InteractionAction]:
        return [self.node_to_interaction(inode) for inode in node.interaction_nodes()]

    @override
    async def forward(
        self,
        snapshot: BrowserSnapshot,
        previous_action_list: Sequence[InteractionAction] | None,
        pagination: PaginationParams,
    ) -> ActionSpace:
        page_content = DomNodeRenderingPipe.forward(snapshot.dom_node, type=DomNodeRenderingType.INTERACTION_ONLY)
        return ActionSpace(
            description=page_content,
            interaction_actions=self.actions(snapshot.dom_node),
        )
