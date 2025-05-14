from collections.abc import Sequence

from notte_core.actions.base import BaseAction
from notte_core.actions.percieved import ActionParameter, PerceivedAction
from notte_core.actions.space import ActionSpace
from notte_core.browser.dom_tree import DomNode, InteractionDomNode
from notte_core.browser.snapshot import BrowserSnapshot
from notte_core.common.config import FrozenConfig
from notte_core.errors.processing import InvalidInternalCheckError
from notte_sdk.types import PaginationParams
from typing_extensions import override

from notte_browser.rendering.interaction_only import InteractionOnlyDomNodeRenderingPipe
from notte_browser.rendering.pipe import (
    DomNodeRenderingConfig,
    DomNodeRenderingPipe,
    DomNodeRenderingType,
)
from notte_browser.tagging.action.base import BaseActionSpacePipe


class SimpleActionSpaceConfig(FrozenConfig):
    rendering: DomNodeRenderingConfig = DomNodeRenderingConfig(type=DomNodeRenderingType.INTERACTION_ONLY)


class SimpleActionSpacePipe(BaseActionSpacePipe):
    def __init__(self, config: SimpleActionSpaceConfig) -> None:
        self.config: SimpleActionSpaceConfig = config

    def node_to_executable(self, node: InteractionDomNode) -> PerceivedAction:
        selectors = node.computed_attributes.selectors
        if selectors is None:
            raise InvalidInternalCheckError(
                check="Node should have an xpath selector",
                url=node.get_url(),
                dev_advice="This should never happen.",
            )
        return PerceivedAction(
            id=node.id,
            category="Interaction action",
            description=InteractionOnlyDomNodeRenderingPipe.render_node(node, self.config.rendering.include_attributes),
            params=[ActionParameter(name="<sample_name>", type="string", values=["<sample_value>"])],
        )

    def actions(self, node: DomNode) -> list[PerceivedAction]:
        return [self.node_to_executable(inode) for inode in node.interaction_nodes()]

    @override
    def forward(
        self,
        snapshot: BrowserSnapshot,
        previous_action_list: Sequence[BaseAction] | None,
        pagination: PaginationParams,
    ) -> ActionSpace:
        page_content = DomNodeRenderingPipe.forward(snapshot.dom_node, config=self.config.rendering)
        return ActionSpace(
            description=page_content,
            interaction_actions=self.actions(snapshot.dom_node),
        )
