from typing import final

from notte.actions.base import Action, PossibleAction
from notte.actions.space import ActionSpace
from notte.browser.context import Context
from notte.llms.service import LLMService
from notte.pipe.filtering import ActionFilteringPipe
from notte.pipe.listing import ActionListingPipe
from notte.pipe.validation import ActionListValidationPipe


@final
class ContextToActionSpacePipe:
    def __init__(
        self,
        action_listing_pipe: ActionListingPipe = ActionListingPipe.SIMPLE_MARKDOWN_TABLE,
        llmserve: LLMService | None = None,
    ) -> None:
        self.action_listing_pipe = action_listing_pipe.get_pipe(llmserve)

    def forward(
        self,
        context: Context,
        previous_action_list: list[Action] | None = None,
        n_trials: int = 2,  # num trial attempts for notte to list actions.
        tresh_complete: float = 0.95,  # requires at least 19 out of 20 actions.
    ) -> ActionSpace:
        # this function assumes tld(previous_actions_list) == tld(context)!
        inodes_ids = [inode.id for inode in context.interaction_nodes()]
        previous_action_list = previous_action_list or []

        # we keep only intersection of current context inodes and previous actions!
        previous_action_list = [action for action in previous_action_list if action.id in inodes_ids]
        possible_space = self.action_listing_pipe.forward(context, previous_action_list)

        actions = self.merge_action_lists(inodes_ids, possible_space.actions, previous_action_list)

        if n_trials == 0 and len(actions) < len(inodes_ids) * tresh_complete:
            raise Exception("notte was unable to properly list all actions for current context")

        if n_trials > 0 and len(actions) < len(inodes_ids) * tresh_complete:
            return self.forward(context, actions, n_trials - 1, tresh_complete)

        actions = ActionFilteringPipe.forward(context, actions)
        return ActionSpace.from_possible(
            possible_space,
            actions=actions,
        )

    @staticmethod
    def merge_action_lists(
        inodes_ids: list[str],
        action_list: list[PossibleAction],
        previous_action_list: list[Action],
    ) -> list[Action]:
        validated_action = ActionListValidationPipe.forward(inodes_ids, action_list)
        # we merge newly validated actions with the misses we got from previous actions!
        valided_action_ids = set([action.id for action in validated_action])
        return validated_action + [
            a for a in previous_action_list if (a.id not in valided_action_ids) and (a.id in inodes_ids)
        ]

    async def forward_async(
        self,
        context: Context,
        previous_action_list: list[Action] | None = None,
        n_trials: int = 2,
        tresh_complete: float = 0.95,
    ) -> ActionSpace:
        return self.forward(context, previous_action_list, n_trials, tresh_complete)
