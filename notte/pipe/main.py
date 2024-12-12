from collections.abc import Sequence

from typing_extensions import final

from notte.actions.base import Action
from notte.actions.space import ActionSpace
from notte.browser.context import Context
from notte.pipe.filtering import ActionFilteringPipe
from notte.pipe.listing import BaseActionListingPipe
from notte.pipe.merging import ActionListMergingPipe
from notte.pipe.validation import ActionListValidationPipe


@final
class ContextToActionSpacePipe:
    def __init__(self, action_listing_pipe: BaseActionListingPipe) -> None:
        self.action_listing_pipe = action_listing_pipe

    async def forward(
        self,
        context: Context,
        previous_action_list: Sequence[Action] | None,
        num_retries: int = 0,
    ) -> ActionSpace:
        action_list = self.action_listing_pipe.forward(context, previous_action_list)
        validated_actions = ActionListValidationPipe.forward(context, action_list)
        if previous_action_list is not None and len(previous_action_list) > 0:
            merged_actions = ActionListMergingPipe.forward(validated_actions, previous_action_list)
        else:
            merged_actions = validated_actions
        if num_retries > 0 and len(merged_actions) < len(context.interaction_nodes()):
            return await self.forward(context, merged_actions, num_retries - 1)
        return ActionFilteringPipe.forward(context, merged_actions)
