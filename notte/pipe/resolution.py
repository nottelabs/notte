from typing import final

from notte.actions.base import Action, ActionParameterValue, ExecutableAction
from notte.browser.context import Context
from notte.browser.driver import BrowserDriver
from notte.browser.node_type import NotteAttributesPost, NotteNode
from notte.browser.snapshot import BrowserSnapshot
from notte.errors.processing import InvalidInternalCheckError
from notte.errors.resolution import (
    FailedNodeResolutionError,
    NodeResolutionAttributeError,
)
from notte.pipe.preprocessing.a11y.conflict_resolution import (
    get_html_selector,
    get_locator_for_node_id,
)


@final
class ActionNodeResolutionPipe:

    def __init__(self, browser: BrowserDriver) -> None:
        self._browser = browser

    async def forward(
        self,
        action: Action,
        params_values: list[ActionParameterValue],
        context: Context,
    ) -> ExecutableAction:
        node = context.node.find(action.id)
        if node is None:
            raise InvalidInternalCheckError(
                check=f"Node with id {action.id} not found in graph",
                url=context.snapshot.metadata.url,
                dev_advice=(
                    "ActionNodeResolutionPipe should only be called on nodes that are present in the graph "
                    "or with valid ids."
                ),
            )

        node.attributes_post = await self.compute_attributes(node, context.snapshot)
        return ExecutableAction(
            id=action.id,
            description=action.description,
            category=action.category,
            params=action.params,
            params_values=params_values,
            node=node,
            status="valid",
            code=None,
        )

    async def compute_attributes(
        self,
        node: NotteNode,
        snapshot: BrowserSnapshot,
    ) -> NotteAttributesPost:
        if node.id is None:
            raise InvalidInternalCheckError(
                url=snapshot.metadata.url,
                check="node.id cannot be None",
                dev_advice="ActionNodeResolutionPipe should only be called on nodes with a valid id.",
            )

        locator = await get_locator_for_node_id(self._browser.page, snapshot.a11y_tree.raw, node.id)
        if locator is None:
            raise FailedNodeResolutionError(node)
        # You can now use the locator for interactions
        text = (await locator.text_content()) or ""
        selectors = await get_html_selector(locator)
        is_editable = await locator.is_editable()
        input_type = None
        if is_editable:
            input_type = await locator.get_attribute("type")
        visible = await locator.is_visible()
        enabled = await locator.is_enabled()

        if selectors is not None:
            return NotteAttributesPost(
                text=text,
                selectors=selectors,
                input_type=input_type,
                editable=is_editable,
                visible=visible,
                enabled=enabled,
            )
        raise NodeResolutionAttributeError(
            node=node,
            error_component=f"selectors (for role='{node.role}' and name='{node.text}')",
        )
