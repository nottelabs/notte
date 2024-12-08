from notte.actions.base import Action


class ActionListMergingPipe:
    @staticmethod
    def forward(llm_actions: list[Action], prev_actions: list[Action]) -> list[Action]:
        llm_actions_ids = {action.id: action for action in llm_actions}
        prev_actions_ids = {action.id: action for action in prev_actions}
        missing_ids = set(prev_actions_ids) - set(llm_actions_ids)

        merged_actions: list[Action] = llm_actions
        for id in missing_ids:
            merged_actions.append(prev_actions_ids[id])

        return merged_actions
