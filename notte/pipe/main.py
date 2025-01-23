from abc import ABC, abstractmethod

from loguru import logger
from typing_extensions import override

from notte.actions.base import Action, PossibleAction
from notte.actions.space import ActionSpace
from notte.browser.context import Context
from notte.errors.actions import NotEnoughActionsListedError
from notte.errors.base import UnexpectedBehaviorError
from notte.llms.service import LLMService
from notte.pipe.document_category import DocumentCategoryPipe
from notte.pipe.filtering import ActionFilteringPipe
from notte.pipe.listing import ActionListingPipe, BaseActionListingPipe
from notte.pipe.validation import ActionListValidationPipe


class BaseContextToActionSpacePipe(ABC):

    @abstractmethod
    def forward(
        self,
        context: Context,
        previous_action_list: list[Action] | None = None,
        min_nb_actions: int | None = None,
        max_nb_actions: int | None = None,
    ) -> ActionSpace:
        raise NotImplementedError()

    async def forward_async(
        self,
        context: Context,
        previous_action_list: list[Action] | None = None,
        min_nb_actions: int | None = None,
        max_nb_actions: int | None = None,
    ) -> ActionSpace:
        return self.forward(
            context,
            previous_action_list,
            min_nb_actions=min_nb_actions,
            max_nb_actions=max_nb_actions,
        )


class ContextToActionSpacePipe(BaseContextToActionSpacePipe):
    def __init__(
        self,
        action_listing_pipe: ActionListingPipe = ActionListingPipe.SIMPLE_MARKDOWN_TABLE,
        categorise_document: bool = True,
        llmserve: LLMService | None = None,
        n_trials: int = 3,
        tresh_complete: float = 0.95,
    ) -> None:
        self.action_listing_pipe: BaseActionListingPipe = action_listing_pipe.get_pipe(llmserve)
        self.doc_categoriser_pipe: DocumentCategoryPipe | None = (
            DocumentCategoryPipe(llmserve) if categorise_document else None
        )
        if tresh_complete > 1.0 or tresh_complete < 0.0:
            raise UnexpectedBehaviorError(
                "tresh_complete must be between 0.0 and 1.0",
                advice="Check the `tresh_complete` parameter in the `ContextToActionSpacePipe` class.",
            )
        if n_trials < 0:
            raise UnexpectedBehaviorError(
                "n_trials must be positive",
                advice="Check the `n_trials` parameter in the `ContextToActionSpacePipe` class.",
            )
        self.tresh_complete: float = tresh_complete
        self.n_trials: int = n_trials

    def get_n_trials(
        self,
        n_trials: int | None = None,
        nb_nodes: int = 0,
        max_nb_actions: int | None = None,
    ) -> int:
        if n_trials is not None:
            return n_trials
        effective_n = nb_nodes // 50
        if max_nb_actions is not None:
            effective_n = min(effective_n, (max_nb_actions // 50) + 1)
        return max(self.n_trials, effective_n)

    def check_enough_actions(
        self,
        inodes_ids: list[str],
        action_list: list[Action],
        min_nb_actions: int | None = None,
        max_nb_actions: int | None = None,
    ) -> bool:
        # gobally check if we have enough actions to proceed.
        n_listed = len(action_list)
        n_required = int(len(inodes_ids) * self.tresh_complete)
        if max_nb_actions is not None:
            n_required = min(n_required, max_nb_actions)
        if n_listed >= n_required and min_nb_actions is None:
            logger.info(f"[ActionListing] Enough actions: {n_listed} >= {n_required}. Stop action listing prematurely.")
            return True
        # for min_nb_actions, we want to check that the first min_nb_actions are in the action_list
        # /!\ the order matter here ! We want to make sure that all the early actions are in the action_list
        listed_ids = set([action.id for action in action_list])
        if min_nb_actions is not None:
            for i, id in enumerate(inodes_ids[:min_nb_actions]):
                if id not in listed_ids:
                    logger.warning(
                        (
                            f"[ActionListing] min_nb_actions = {min_nb_actions} but action {id} "
                            f"({i+1}th action) is not in the action list. Retry listng."
                        )
                    )
                    return False
            logger.info(
                (
                    f"[ActionListing] Min_nb_actions = {min_nb_actions} and all actions are in the action list."
                    " Stop action listing prematurely."
                )
            )
            return True

        logger.warning(
            (
                f"Not enough actions listed: {len(inodes_ids)} total, "
                f"{n_required} required for completion but only {n_listed} listed"
            )
        )
        return False

    def forward_unfiltered(
        self,
        context: Context,
        previous_action_list: list[Action] | None = None,
        n_trials: int | None = None,
        min_nb_actions: int | None = None,
        max_nb_actions: int | None = None,
    ) -> ActionSpace:
        # this function assumes tld(previous_actions_list) == tld(context)!
        inodes_ids = [inode.id for inode in context.interaction_nodes()]
        previous_action_list = previous_action_list or []
        n_trials = self.get_n_trials(n_trials, nb_nodes=len(inodes_ids), max_nb_actions=max_nb_actions)

        # we keep only intersection of current context inodes and previous actions!
        previous_action_list = [action for action in previous_action_list if action.id in inodes_ids]
        # TODO: question, can we already perform a `check_enough_actions` here ?
        possible_space = self.action_listing_pipe.forward(context, previous_action_list)
        merged_actions = self.merge_action_lists(inodes_ids, possible_space.actions, previous_action_list)
        # check if we have enough actions to proceed.
        completed = self.check_enough_actions(
            inodes_ids, merged_actions, min_nb_actions=min_nb_actions, max_nb_actions=max_nb_actions
        )
        if not completed and n_trials == 0:
            raise NotEnoughActionsListedError(
                n_trials=self.get_n_trials(None, nb_nodes=len(inodes_ids), max_nb_actions=max_nb_actions),
                n_actions=len(inodes_ids),
                threshold=self.tresh_complete,
            )

        if not completed and n_trials > 0:
            logger.info(f"[ActionListing] Retry listing actions with {n_trials} trials left.")
            return self.forward_unfiltered(
                context,
                merged_actions,
                n_trials=n_trials - 1,
                min_nb_actions=min_nb_actions,
                max_nb_actions=max_nb_actions,
            )

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
        min_nb_actions: int | None = None,
        max_nb_actions: int | None = None,
    ):
        space = self.forward_unfiltered(
            context,
            previous_action_list,
            min_nb_actions=min_nb_actions,
            max_nb_actions=max_nb_actions,
        )
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
