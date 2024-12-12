from collections.abc import Sequence

from notte.actions.base import Action


class ActionListMergingPipe:
    @staticmethod
    def forward(llm_actions: Sequence[Action], prev_actions: Sequence[Action]) -> Sequence[Action]:
        llm_actions_ids = {action.id: action for action in llm_actions}
        prev_actions_ids = {action.id: action for action in prev_actions}
        missing_ids = set(prev_actions_ids) - set(llm_actions_ids)

        merged_actions: list[Action] = [a for a in llm_actions]
        for id in missing_ids:
            merged_actions.append(prev_actions_ids[id])

        return merged_actions
