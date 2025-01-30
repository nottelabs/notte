from abc import ABC, abstractmethod

from loguru import logger
from pydantic import BaseModel
from typing_extensions import override

from notte.actions.base import Action, PossibleAction
from notte.actions.space import ActionSpace
from notte.browser.processed_snapshot import ProcessedBrowserSnapshot
from notte.errors.actions import NotEnoughActionsListedError
from notte.errors.base import UnexpectedBehaviorError
from notte.llms.service import LLMService
from notte.pipe.action_listing.base import BaseActionListingPipe
from notte.pipe.action_listing.pipe import ActionListingConfig, MainActionListingPipe
from notte.pipe.document_category import DocumentCategoryPipe
from notte.pipe.filtering import ActionFilteringPipe
from notte.pipe.validation import ActionListValidationPipe
from notte.sdk.types import PaginationObserveRequest


class ContextToActionSpaceConfig(BaseModel):
    listing: ActionListingConfig = ActionListingConfig()
    doc_categorisation: bool = True
    # completion config
    required_action_coverage: float = 0.95
    max_listing_trials: int = 3

    def __post_init__(self):
        if self.required_action_coverage > 1.0 or self.required_action_coverage < 0.0:
            raise UnexpectedBehaviorError(
                "'required_action_coverage' must be between 0.0 and 1.0",
                advice="Check the `required_action_coverage` parameter in the `ContextToActionSpaceConfig` class.",
            )
        if self.max_listing_trials < 0:
            raise UnexpectedBehaviorError(
                "'max_listing_trials' must be positive",
                advice="Check the `max_listing_trials` parameter in the `ContextToActionSpaceConfig` class.",
            )


class BaseContextToActionSpacePipe(ABC):
    @abstractmethod
    def forward(
        self,
        context: ProcessedBrowserSnapshot,
        previous_action_list: list[Action] | None,
        pagination: PaginationObserveRequest,
    ) -> ActionSpace:
        raise NotImplementedError()

    async def forward_async(
        self,
        context: ProcessedBrowserSnapshot,
        previous_action_list: list[Action] | None,
        pagination: PaginationObserveRequest,
    ) -> ActionSpace:
        return self.forward(context, previous_action_list, pagination)


class ContextToActionSpacePipe(BaseContextToActionSpacePipe):
    def __init__(
        self,
        llmserve: LLMService | None = None,
        config: ContextToActionSpaceConfig | None = None,
    ) -> None:
        self.config: ContextToActionSpaceConfig = config or ContextToActionSpaceConfig()
        self.action_listing_pipe: BaseActionListingPipe = MainActionListingPipe(llmserve, config=self.config.listing)
        self.doc_categoriser_pipe: DocumentCategoryPipe | None = (
            DocumentCategoryPipe(llmserve) if self.config.doc_categorisation else None
        )

    def get_n_trials(
        self,
        nb_nodes: int = 0,
        max_nb_actions: int | None = None,
    ) -> int:
        effective_n = nb_nodes // 50
        if max_nb_actions is not None:
            effective_n = min(effective_n, (max_nb_actions // 50) + 1)
        return max(self.config.max_listing_trials, effective_n)

    def check_enough_actions(
        self,
        inodes_ids: list[str],
        action_list: list[Action],
        pagination: PaginationObserveRequest,
    ) -> bool:
        # gobally check if we have enough actions to proceed.
        n_listed = len(action_list)
        n_required = int(len(inodes_ids) * self.config.required_action_coverage)
        n_required = min(n_required, pagination.max_nb_actions)
        if n_listed >= n_required and pagination.min_nb_actions is None:
            logger.info(f"[ActionListing] Enough actions: {n_listed} >= {n_required}. Stop action listing prematurely.")
            return True
        # for min_nb_actions, we want to check that the first min_nb_actions are in the action_list
        # /!\ the order matter here ! We want to make sure that all the early actions are in the action_list
        listed_ids = set([action.id for action in action_list])
        if pagination.min_nb_actions is not None:
            for i, id in enumerate(inodes_ids[: pagination.min_nb_actions]):
                if id not in listed_ids:
                    logger.warning(
                        (
                            f"[ActionListing] min_nb_actions = {pagination.min_nb_actions} but action {id} "
                            f"({i+1}th action) is not in the action list. Retry listng."
                        )
                    )
                    return False
            logger.info(
                (
                    f"[ActionListing] Min_nb_actions = {pagination.min_nb_actions} and all "
                    "actions are in the action list. Stop action listing prematurely."
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
        context: ProcessedBrowserSnapshot,
        previous_action_list: list[Action] | None,
        pagination: PaginationObserveRequest,
        n_trials: int,
    ) -> ActionSpace:
        # this function assumes tld(previous_actions_list) == tld(context)!
        inodes_ids = [inode.id for inode in context.interaction_nodes()]
        previous_action_list = previous_action_list or []
        # we keep only intersection of current context inodes and previous actions!
        previous_action_list = [action for action in previous_action_list if action.id in inodes_ids]
        # TODO: question, can we already perform a `check_enough_actions` here ?
        possible_space = self.action_listing_pipe.forward(context, previous_action_list)
        merged_actions = self.merge_action_lists(inodes_ids, possible_space.actions, previous_action_list)
        # check if we have enough actions to proceed.
        completed = self.check_enough_actions(inodes_ids, merged_actions, pagination)
        if not completed and n_trials == 0:
            raise NotEnoughActionsListedError(
                n_trials=self.get_n_trials(nb_nodes=len(inodes_ids), max_nb_actions=pagination.max_nb_actions),
                n_actions=len(inodes_ids),
                threshold=self.config.required_action_coverage,
            )

        if not completed and n_trials > 0:
            logger.info(f"[ActionListing] Retry listing actions with {n_trials} trials left.")
            return self.forward_unfiltered(
                context,
                merged_actions,
                n_trials=n_trials - 1,
                pagination=pagination,
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
        context: ProcessedBrowserSnapshot,
        previous_action_list: list[Action] | None,
        pagination: PaginationObserveRequest,
    ):
        space = self.forward_unfiltered(
            context,
            previous_action_list,
            pagination=pagination,
            n_trials=self.get_n_trials(
                nb_nodes=len(context.interaction_nodes()),
                max_nb_actions=pagination.max_nb_actions,
            ),
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
