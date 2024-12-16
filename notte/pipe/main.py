from typing import final

from notte.actions.base import Action
from notte.actions.space import ActionSpace
from notte.browser.context import Context
from notte.browser.node_type import NotteNode
from notte.llms.service import LLMService
from notte.pipe.filtering import ActionFilteringPipe
from notte.pipe.listing import ActionListingPipe
from notte.pipe.validation import ActionListValidationPipe
from notte.utils.partition import merge_trees, partial_tree_by_path, partition, split


@final
class ContextToActionSpacePipe:
    def __init__(
        self,
        action_listing_pipe: ActionListingPipe = ActionListingPipe.SIMPLE_MARKDOWN_TABLE,
        llmserve: LLMService | None = None,
    ) -> None:
        self.action_listing_pipe = action_listing_pipe.get_pipe(llmserve)

    def _forward(
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
        action_list = self.action_listing_pipe.forward(context, previous_action_list)
        validated_action = ActionListValidationPipe.forward(inodes_ids, action_list)

        # we merge newly validated actions with the misses we got from previous actions!
        valided_action_ids = [action.id for action in validated_action]
        actions: list[Action] = validated_action + [a for a in previous_action_list if a.id not in valided_action_ids]

        if n_trials == 0 and len(actions) < len(inodes_ids) * tresh_complete:
            raise Exception("notte was unable to properly list all actions for current context")

        if n_trials > 0 and len(actions) < len(inodes_ids) * tresh_complete:
            return self.forward(context, actions, n_trials - 1, tresh_complete)

        actions = ActionFilteringPipe.forward(context, actions)
        return ActionSpace(_actions=actions)

    def forward(
        self,
        context: Context,
        previous_action_list: list[Action] | None = None,
        n_trials: int = 2,
        tresh_complete: float = 0.95,
        gamma: int = 12000,  # num chars threshold. (token estimated.)
    ) -> ActionSpace:
        # triggers NotteNode[._chars,._path] calculation at build time.
        _ = context.format(context.node)

        # if the node size fits, we can proceed with the action listing.
        if context.node._chars <= gamma:
            return self._forward(context, previous_action_list, n_trials, tresh_complete)

        # if the node is too big, we split it into subnodes.
        subnodes = split(context.node, gamma)
        chars = [subnode._chars for subnode in subnodes]
        paths = [subnode._path for subnode in subnodes]
        partitions = partition(chars, gamma)

        trees: list[NotteNode] = []
        for _partition in partitions:
            if len(_partition) > 1:
                _paths = [paths[i] for i in _partition]
                partials = [partial_tree_by_path(context.node, path) for path in _paths]
                merged = merge_trees(partials)
                if merged is not None:
                    trees.append(merged)
            else:
                path = paths[_partition[0]]
                partial = partial_tree_by_path(context.node, path)
                trees.append(partial)

        # _forward for each tree, with incremental listing.
        space: ActionSpace | None = None
        _previous_action_list: list[Action] = previous_action_list or []
        for tree in trees:
            ctx = Context(node=tree, snapshot=context.snapshot)
            _space = self._forward(ctx, _previous_action_list, n_trials, tresh_complete)
            _previous_action_list.extend(_space.actions("all"))
            space = _space

        if space is None:
            raise Exception("fatal error | should not happen.")

        return space
