from loguru import logger
from notte.actions.base import Action, PossibleAction
from notte.actions.parsing import parse_table
from notte.actions.space import ActionSpace
from notte.browser.context import Context
from notte.llms.engine import StructuredContent
from notte.llms.service import LLMService


class ActionListingPipe:
    def __init__(self) -> None:
        self.llmserve: LLMService = LLMService()

    def forward(
        self, context: Context, previous_action_list: list[Action] | None = None
    ) -> list[PossibleAction]:
        if previous_action_list is not None and len(previous_action_list) > 0:
            return self.forward_incremental(context, previous_action_list)

        ctx = context.markdown_description()

        max_tries = 1
        tries = 0
        while tries < max_tries:
            try:
                result = self.get_action_list(ctx)
                return result
            except Exception:
                tries += 1
                if tries == max_tries:
                    raise Exception(
                        f"Failed to get action list after {max_tries} tries"
                    )
        # Add explicit return to satisfy mypy
        raise Exception("Should never reach here")

    def get_action_list(self, document: str) -> list[PossibleAction]:
        response = self.llmserve.completion(
            "action-listing/optim", {"document": document}
        )
        sc = StructuredContent(outer_tag="action-listing")
        if response.choices[0].message.content is None:  # type: ignore
            raise ValueError("No content in response")
        text = sc.extract(response.choices[0].message.content)  # type: ignore
        possible_actions = parse_table(text)
        return possible_actions

    def forward_incremental(
        self, context: Context, previous_action_list: list[Action]
    ) -> list[PossibleAction]:
        try:
            logger.info("🚀 forward incremental")
            ctx = context.subgraph_without(previous_action_list).markdown_description()
            _space = ActionSpace(_actions=previous_action_list)
            response = self.llmserve.completion(
                "action-listing-incr",
                {
                    "document": ctx,
                    "previous_action_list": _space.markdown("valid"),
                },
            )
            sc = StructuredContent(outer_tag="action-listing")
            if response.choices[0].message.content is None:  # type: ignore
                raise ValueError("No content in response")
            text = sc.extract(response.choices[0].message.content)  # type: ignore
            possible_actions = parse_table(text)
            return possible_actions
        except Exception:
            return [
                PossibleAction(
                    id=act.id,
                    description=act.description,
                    category=act.category,
                    params=act.params,
                )
                for act in previous_action_list
            ]
