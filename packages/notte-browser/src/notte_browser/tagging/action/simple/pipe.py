from collections.abc import Sequence
from typing import Self

from notte_core.actions.base import ActionParameterValue, ExecutableAction
from notte_core.browser.allowlist import ActionAllowList
from notte_core.browser.dom_tree import DomNode, InteractionDomNode
from notte_core.browser.snapshot import BrowserSnapshot
from notte_core.common.config import FrozenConfig
from notte_core.controller.actions import BaseAction
from notte_core.controller.space import ActionSpace
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

    def set_allow_list(self: Self, allow_list: ActionAllowList) -> Self:
        return self._copy_and_validate(rendering=self.rendering.set_allow_list(allow_list))


class SimpleActionSpacePipe(BaseActionSpacePipe):
    def __init__(self, config: SimpleActionSpaceConfig) -> None:
        self.config: SimpleActionSpaceConfig = config

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
            description=InteractionOnlyDomNodeRenderingPipe.render_node(node, self.config.rendering.include_attributes),
            # node=ResolvedLocator(
            #     selector=selectors,
            #     is_editable=False,
            #     input_type=None,
            #     role=node.role,
            # ),
            node=node,
            params_values=[
                ActionParameterValue(
                    name="value",
                    value="<sample_value>",
                )
            ],
        )

    def actions(self, node: DomNode) -> list[BaseAction]:
        actions: list[BaseAction] = []

        for inode in node.interaction_nodes():
            actions.append(self.node_to_executable(inode))

        return actions

    @override
    def forward(
        self,
        snapshot: BrowserSnapshot,
        previous_action_list: Sequence[BaseAction] | None,
        pagination: PaginationParams,
    ) -> ActionSpace:
        allow_list = self.config.rendering.allow_list
        dom_node = snapshot.dom_node

        import logging

        logging.warning(f"{allow_list=}")

        if allow_list is not None:
            dom_node = allow_list.filter_tree(dom_node)

        page_content = DomNodeRenderingPipe.forward(dom_node, config=self.config.rendering)
        return ActionSpace(
            description=page_content,
            raw_actions=self.actions(dom_node),
        )
