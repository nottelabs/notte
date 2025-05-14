from collections.abc import Sequence

from loguru import logger
from notte_core.actions.base import BaseAction
from notte_core.actions.percieved import PerceivedAction
from notte_core.actions.space import ActionSpace
from notte_core.browser.node_type import NodeCategory
from notte_core.browser.snapshot import BrowserSnapshot
from notte_core.common.config import FrozenConfig
from notte_core.errors.actions import NotEnoughActionsListedError
from notte_core.errors.base import UnexpectedBehaviorError
from notte_core.errors.processing import NodeFilteringResultsInEmptyGraph
from notte_core.llms.service import LLMService
from notte_sdk.types import PaginationParams
from typing_extensions import override

from notte_browser.tagging.action.base import BaseActionSpacePipe
from notte_browser.tagging.action.llm_taging.base import BaseActionListingPipe
from notte_browser.tagging.action.llm_taging.filtering import ActionFilteringPipe
from notte_browser.tagging.action.llm_taging.listing import (
    ActionListingConfig,
    MainActionListingPipe,
)
from notte_browser.tagging.action.llm_taging.validation import ActionListValidationPipe
from notte_browser.tagging.page import PageCategoryPipe
from notte_browser.tagging.types import PossibleAction


class LlmActionSpaceConfig(FrozenConfig):
    listing: ActionListingConfig = ActionListingConfig()
    doc_categorisation: bool = True
    # completion config
    required_action_coverage: float = 0.95
    max_listing_trials: int = 3
    include_images: bool = False

    def __post_init__(self):
        if self.required_action_coverage > 1.0 or self.required_action_coverage < 0.0:
            raise UnexpectedBehaviorError(
                "'required_action_coverage' must be between 0.0 and 1.0",
                advice="Check the `required_action_coverage` parameter in the `LlmActionSpaceConfig` class.",
            )
        if self.max_listing_trials < 0:
            raise UnexpectedBehaviorError(
                "'max_listing_trials' must be positive",
                advice="Check the `max_listing_trials` parameter in the `LlmActionSpaceConfig` class.",
            )


class LlmActionSpacePipe(BaseActionSpacePipe):
    def __init__(
        self,
        llmserve: LLMService,
        config: LlmActionSpaceConfig,
    ) -> None:
        self.config: LlmActionSpaceConfig = config
        self.action_listing_pipe: BaseActionListingPipe = MainActionListingPipe(llmserve, config=self.config.listing)
        self.doc_categoriser_pipe: PageCategoryPipe | None = (
            PageCategoryPipe(llmserve, verbose=self.config.verbose) if self.config.doc_categorisation else None
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
        action_list: Sequence[PerceivedAction],
        pagination: PaginationParams,
    ) -> bool:
        # gobally check if we have enough actions to proceed.
        n_listed = len(action_list)
        n_required = int(len(inodes_ids) * self.config.required_action_coverage)
        n_required = min(n_required, pagination.max_nb_actions)
        if n_listed >= n_required and pagination.min_nb_actions is None:
            if self.config.verbose:
                logger.info(
                    f"[ActionListing] Enough actions: {n_listed} >= {n_required}. Stop action listing prematurely."
                )
            return True
        # for min_nb_actions, we want to check that the first min_nb_actions are in the action_list
        # /!\ the order matter here ! We want to make sure that all the early actions are in the action_list
        listed_ids = set([action.id for action in action_list])
        if pagination.min_nb_actions is not None:
            for i, id in enumerate(inodes_ids[: pagination.min_nb_actions]):
                if id not in listed_ids:
                    if self.config.verbose:
                        logger.warning(
                            f"[ActionListing] min_nb_actions = {pagination.min_nb_actions} but action {id} "
                            + f"({i + 1}th action) is not in the action list. Retry listng."
                        )
                    return False
            if self.config.verbose:
                logger.info(
                    (
                        f"[ActionListing] Min_nb_actions = {pagination.min_nb_actions} and all "
                        "actions are in the action list. Stop action listing prematurely."
                    )
                )
            return True

        if self.config.verbose:
            logger.warning(
                (
                    f"Not enough actions listed: {len(inodes_ids)} total, "
                    f"{n_required} required for completion but only {n_listed} listed"
                )
            )
        return False

    def forward_unfiltered(
        self,
        snapshot: BrowserSnapshot,
        previous_action_list: Sequence[PerceivedAction] | None,
        pagination: PaginationParams,
        n_trials: int,
    ) -> ActionSpace:
        # this function assumes tld(previous_actions_list) == tld(context)!
        inodes_ids = [inode.id for inode in snapshot.interaction_nodes()]
        previous_action_list = previous_action_list or []
        # we keep only intersection of current context inodes and previous actions!
        previous_action_list = [action for action in previous_action_list if action.id in inodes_ids]
        # TODO: question, can we already perform a `check_enough_actions` here ?
        possible_space = self.action_listing_pipe.forward(snapshot, previous_action_list)
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
            if self.config.verbose:
                logger.info(f"[ActionListing] Retry listing actions with {n_trials} trials left.")
            return self.forward_unfiltered(
                snapshot,
                merged_actions,
                n_trials=n_trials - 1,
                pagination=pagination,
            )

        space = ActionSpace(
            description=possible_space.description,
            interaction_actions=merged_actions,
        )
        # categorisation should only be done after enough actions have been listed to avoid unecessary LLM calls.
        if self.doc_categoriser_pipe:
            space.category = self.doc_categoriser_pipe.forward(snapshot, space)
        return space

    def tagging_context(self, snapshot: BrowserSnapshot) -> BrowserSnapshot:
        if self.config.include_images:
            return snapshot
        if self.config.verbose:
            logger.info("🏞️ Excluding images from the action tagging process")
        _snapshot = snapshot.subgraph_without(actions=[], roles=NodeCategory.IMAGE.roles())
        if _snapshot is None:
            raise NodeFilteringResultsInEmptyGraph(
                url=snapshot.metadata.url,
                operation=f"subtree_without(roles={NodeCategory.IMAGE.roles()})",
            )
        return _snapshot

    @override
    def forward(
        self,
        snapshot: BrowserSnapshot,
        previous_action_list: Sequence[BaseAction] | None,
        pagination: PaginationParams,
    ) -> ActionSpace:
        # TODO: handle the typing of this properly later on
        cast_previous_action_list: Sequence[PerceivedAction] | None = previous_action_list  # type: ignore
        _snapshot = self.tagging_context(snapshot)

        space = self.forward_unfiltered(
            _snapshot,
            cast_previous_action_list,
            pagination=pagination,
            n_trials=self.get_n_trials(
                nb_nodes=len(snapshot.interaction_nodes()),
                max_nb_actions=pagination.max_nb_actions,
            ),
        )
        filtered_actions = ActionFilteringPipe.forward(_snapshot, space.interaction_actions)
        return ActionSpace(
            description=space.description,
            interaction_actions=filtered_actions,
            category=space.category,
        )

    def merge_action_lists(
        self,
        inodes_ids: list[str],
        actions: Sequence[PossibleAction],
        previous_action_list: Sequence[PerceivedAction],
    ) -> Sequence[PerceivedAction]:
        validated_action = ActionListValidationPipe.forward(
            inodes_ids,
            actions,
            previous_action_list,
            verbose=self.config.verbose,
        )
        # we merge newly validated actions with the misses we got from previous actions!
        valided_action_ids = set([action.id for action in validated_action])
        return validated_action + [
            a for a in previous_action_list if (a.id not in valided_action_ids) and (a.id in inodes_ids)
        ]
