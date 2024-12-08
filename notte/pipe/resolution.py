from typing import final

from notte.actions.base import Action, ActionParameterValue, ExecutableAction
from notte.browser.context import Context
from notte.browser.driver import BrowserDriver
from notte.browser.node_type import NotteAttributesPost, NotteNode
from notte.browser.snapshot import BrowserSnapshot
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
            raise ValueError(f"Node with id {action.id} not found in graph")

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
            raise ValueError(f"Node with id {node.id} not found in graph")

        locator = await get_locator_for_node_id(self._browser.page, snapshot.a11y_tree.raw, node.id)
        if locator is None:
            raise Exception(f"No locator found for node with ID {node.id}")
        # You can now use the locator for interactions
        text = (await locator.text_content()) or ""
        selectors = await get_html_selector(locator)
        is_editable = await locator.is_editable()
        input_type = None
        if is_editable:
            input_type = await locator.get_attribute("type")

        if selectors is not None:
            return NotteAttributesPost(
                text=text,
                selectors=selectors,
                input_type=input_type,
                editable=is_editable,
            )
        raise ValueError(f"No locator found for '{node.text}' with role '{node.role}'")
