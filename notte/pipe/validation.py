from loguru import logger
from notte.actions.base import Action, PossibleAction
from notte.browser.context import Context


class ActionListValidationPipe:

    @staticmethod
    def forward(context: Context, actions: list[PossibleAction]) -> list[Action]:
        inodes = context.interaction_nodes()
        inodes_ids = [inode.id for inode in inodes]
        actions_ids = {action.id: action for action in actions}
        hallucinated_ids = [id for id in actions_ids if id not in inodes_ids]
        validated_actions: list[Action] = []
        missed = 0
        for id in set([inode.id for inode in inodes if inode.id is not None]):
            if id in actions_ids:
                validated_actions.append(
                    Action(
                        id=id,
                        description=actions_ids[id].description,
                        category=actions_ids[id].category,
                        params=actions_ids[id].params,
                        status="valid",
                    )
                )

            else:
                missed += 1

        if len(hallucinated_ids) > 0:
            logger.info(f"Hallucinated actions: {len(hallucinated_ids)}")
            # TODO: log them into DB.

        if missed > 0:
            logger.info(f"Missed actions: {missed}")
            # TODO: log them into DB.

        return validated_actions
