from abc import ABC, abstractmethod

from typing_extensions import override

from notte.actions.base import Action, PossibleAction
from notte.actions.space import ActionSpace
from notte.browser.context import Context
from notte.llms.service import LLMService
from notte.pipe.document_category import DocumentCategoryPipe
from notte.pipe.filtering import ActionFilteringPipe
from notte.pipe.listing import ActionListingPipe, BaseActionListingPipe
from notte.pipe.validation import ActionListValidationPipe


class BaseContextToActionSpacePipe(ABC):

    @abstractmethod
    def forward(self, context: Context, previous_action_list: list[Action] | None = None) -> ActionSpace:
        raise NotImplementedError()

    async def forward_async(
        self,
        context: Context,
        previous_action_list: list[Action] | None = None,
    ) -> ActionSpace:
        return self.forward(context, previous_action_list)


class ContextToActionSpacePipe(BaseContextToActionSpacePipe):
    def __init__(
        self,
        action_listing_pipe: ActionListingPipe = ActionListingPipe.SIMPLE_MARKDOWN_TABLE,
        categorise_document: bool = True,
        llmserve: LLMService | None = None,
        n_trials: int = 2,
        tresh_complete: float = 0.95,
    ) -> None:
        self.action_listing_pipe: BaseActionListingPipe = action_listing_pipe.get_pipe(llmserve)
        self.doc_categoriser_pipe: DocumentCategoryPipe | None = (
            DocumentCategoryPipe(llmserve) if categorise_document else None
        )
        self.tresh_complete: float = tresh_complete
        self.n_trials: int = n_trials

    def forward_unfiltered(
        self,
        context: Context,
        previous_action_list: list[Action] | None = None,
        n_trials: int | None = None,
    ) -> ActionSpace:
        # this function assumes tld(previous_actions_list) == tld(context)!
        inodes_ids = [inode.id for inode in context.interaction_nodes()]
        previous_action_list = previous_action_list or []
        n_trials = n_trials if n_trials is not None else self.n_trials

        # we keep only intersection of current context inodes and previous actions!
        previous_action_list = [action for action in previous_action_list if action.id in inodes_ids]
        possible_space = self.action_listing_pipe.forward(context, previous_action_list)
        merged_actions = self.merge_action_lists(inodes_ids, possible_space.actions, previous_action_list)
        # check if we have enough actions to proceed.
        n_required, n_listed = len(inodes_ids) * self.tresh_complete, len(merged_actions)
        if n_trials == 0 and n_listed < n_required:
            raise Exception(
                (
                    f"Not enough actions listed: {len(inodes_ids)} total, {n_required} required, {n_listed} listed"
                    f" ({len(previous_action_list)} from previous and {len(possible_space.actions)} from new)"
                )
            )

        if n_trials > 0 and n_listed < n_required:
            return self.forward_unfiltered(context, merged_actions, n_trials - 1)

        space = ActionSpace(
            description=possible_space.description,
            _actions=merged_actions,
        )
        # categorisation should only be done after enough actions have been listed to avoid unecessary LLM calls.
        if self.doc_categoriser_pipe:
            space.category = self.doc_categoriser_pipe.forward(context, space)
        return space

    @override
    def forward(
        self,
        context: Context,
        previous_action_list: list[Action] | None = None,
    ):
        space = self.forward_unfiltered(context, previous_action_list)
        filtered_actions = ActionFilteringPipe.forward(context, space._actions)
        return space.with_actions(filtered_actions)

    def merge_action_lists(
        self,
        inodes_ids: list[str],
        actions: list[PossibleAction],
        previous_action_list: list[Action],
    ) -> list[Action]:
        validated_action = ActionListValidationPipe.forward(inodes_ids, actions, previous_action_list)
        # we merge newly validated actions with the misses we got from previous actions!
        valided_action_ids = set([action.id for action in validated_action])
        return validated_action + [
            a for a in previous_action_list if (a.id not in valided_action_ids) and (a.id in inodes_ids)
        ]
