from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, ClassVar

from loguru import logger
from typing_extensions import override

from notte.actions.base import Action, PossibleAction
from notte.actions.parsing import ActionListingParser
from notte.actions.space import ActionSpace, PossibleActionSpace
from notte.browser.context import Context
from notte.common.tracer import LlmParsingErrorFileTracer
from notte.llms.engine import StructuredContent
from notte.llms.service import LLMService


class BaseActionListingPipe(ABC):

    def __init__(self, llmserve: LLMService | None = None) -> None:
        self.llmserve: LLMService = llmserve or LLMService()

    @abstractmethod
    def forward(self, context: Context, previous_action_list: list[Action] | None = None) -> PossibleActionSpace:
        pass

    def llm_completion(self, prompt_id: str, variables: dict[str, Any]) -> str:
        response = self.llmserve.completion(prompt_id, variables)
        if response.choices[0].message.content is None:  # type: ignore
            raise ValueError("LLM completion failed. No content in response")
        return response.choices[0].message.content  # type: ignore

    @abstractmethod
    def forward_incremental(
        self,
        context: Context,
        previous_action_list: list[Action],
    ) -> PossibleActionSpace:
        """
        This method is used to get the next action list based on the previous action list.

        /!\\ This was designed to only be used in the `forward` method when the previous action list is not empty.
        """
        raise NotImplementedError("forward_incremental")


class BaseSimpleActionListingPipe(BaseActionListingPipe, ABC):

    def __init__(
        self,
        llmserve: LLMService | None,
        prompt_id: str,
        incremental_prompt_id: str,
        parser: ActionListingParser,
    ) -> None:
        super().__init__(llmserve)
        self.parser: ActionListingParser = parser
        self.prompt_id: str = prompt_id
        self.incremental_prompt_id: str = incremental_prompt_id

    @abstractmethod
    def get_prompt_variables(
        self, context: Context, previous_action_list: list[Action] | None = None
    ) -> dict[str, Any]:
        raise NotImplementedError("get_prompt_variables")

    def parse_action_listing(self, response: str) -> list[PossibleAction]:
        sc = StructuredContent(
            outer_tag="action-listing",
            inner_tag="markdown",
        )
        text = sc.extract(
            response,  # type: ignore
            fail_if_final_tag=False,
            fail_if_inner_tag=False,
        )
        try:
            return self.parser.parse(text)
        except Exception as e:
            logger.error(f"Failed to parse action listing: with content: \n {text}")
            raise e

    def parse_webpage_description(self, response: str) -> str:
        sc = StructuredContent(
            outer_tag="document-summary",
            next_outer_tag="document-analysis",
        )
        text = sc.extract(
            response,  # type: ignore
            fail_if_inner_tag=False,
            fail_if_final_tag=False,
            fail_if_next_outer_tag=False,
        )
        return text

    @override
    def forward(
        self,
        context: Context,
        previous_action_list: list[Action] | None = None,
    ) -> PossibleActionSpace:
        if previous_action_list is not None and len(previous_action_list) > 0:
            return self.forward_incremental(context, previous_action_list)
        if len(context.interaction_nodes()) == 0:
            return PossibleActionSpace(
                description="Description not available because no interaction actions found",
                actions=[],
            )
        variables = self.get_prompt_variables(context, previous_action_list)
        response = self.llm_completion(self.prompt_id, variables)
        return PossibleActionSpace(
            description=self.parse_webpage_description(response),
            actions=self.parse_action_listing(response),
        )

    @override
    def forward_incremental(
        self,
        context: Context,
        previous_action_list: list[Action],
    ) -> PossibleActionSpace:
        incremental_context = context.subgraph_without(previous_action_list)
        if incremental_context is None:
            logger.error(
                (
                    "No nodes left in context after filtering of exesting actions "
                    f"for url {context.snapshot.metadata.url}. "
                    "Returning previous action list..."
                )
            )
            return PossibleActionSpace(
                description="",
                actions=[
                    PossibleAction(
                        id=act.id,
                        description=act.description,
                        category=act.category,
                        params=act.params,
                    )
                    for act in previous_action_list
                ],
            )
        total_length, incremental_length = len(context.markdown_description()), len(
            incremental_context.markdown_description()
        )
        reduction_perc = (total_length - incremental_length) / total_length * 100
        logger.info(f"🚀 Forward incremental reduces context length by {reduction_perc:.2f}%")
        variables = self.get_prompt_variables(incremental_context, previous_action_list)
        response = self.llm_completion(self.incremental_prompt_id, variables)
        return PossibleActionSpace(
            description=self.parse_webpage_description(response),
            actions=self.parse_action_listing(response),
        )


class RetryPipeWrapper(BaseActionListingPipe):
    tracer: ClassVar[LlmParsingErrorFileTracer] = LlmParsingErrorFileTracer()

    def __init__(
        self,
        pipe: BaseActionListingPipe,
        max_tries: int = 3,
    ):
        super().__init__(pipe.llmserve)
        self.pipe: BaseActionListingPipe = pipe
        self.max_tries: int = max_tries

    @override
    def forward(self, context: Context, previous_action_list: list[Action] | None = None) -> PossibleActionSpace:
        errors: list[str] = []
        for _ in range(self.max_tries):
            try:
                out = self.pipe.forward(context, previous_action_list)
                self.tracer.trace(
                    status="success",
                    pipe_name=self.pipe.__class__.__name__,
                    nb_retries=len(errors),
                    error_msgs=errors,
                )
                return out
            except Exception as e:
                if "Please reduce the length of the messages or completions" in str(e):
                    # this is a known error that happens when the context is too long
                    # we should not retry in this case (nothing is going to change)
                    raise RuntimeError("Context size too large. Please update processing pipeline. Error: " + str(e))
                logger.warning(f"failed to parse action list but retrying. Start of error msg: {str(e)[:200]}...")
                errors.append(str(e))
        self.tracer.trace(
            status="failure",
            pipe_name=self.pipe.__class__.__name__,
            nb_retries=len(errors),
            error_msgs=errors,
        )
        raise Exception(f"Failed to get action list after max tries with errors: {errors}")

    @override
    def forward_incremental(
        self,
        context: Context,
        previous_action_list: list[Action],
    ) -> PossibleActionSpace:
        for _ in range(self.max_tries):
            try:
                return self.pipe.forward_incremental(context, previous_action_list)
            except Exception:
                pass
        logger.error("Failed to get action list after max tries => returning previous action list")
        return PossibleActionSpace(
            # TODO: get description from previous action list
            description="",
            actions=[
                PossibleAction(
                    id=act.id,
                    description=act.description,
                    category=act.category,
                    params=act.params,
                )
                for act in previous_action_list
            ],
        )


class MarkdownTableActionListingPipe(BaseSimpleActionListingPipe):

    def __init__(self, llmserve: LLMService | None = None) -> None:
        super().__init__(
            llmserve=llmserve,
            prompt_id="action-listing/optim",
            incremental_prompt_id="action-listing-incr",
            parser=ActionListingParser.TABLE,
        )

    @override
    def get_prompt_variables(
        self, context: Context, previous_action_list: list[Action] | None = None
    ) -> dict[str, Any]:
        vars = {"document": context.markdown_description()}
        if previous_action_list is not None:
            vars["previous_action_list"] = ActionSpace(_actions=previous_action_list, description="").markdown(
                "all", include_special=False
            )
        return vars


class ActionListingPipe(Enum):
    SIMPLE_MARKDOWN_TABLE = "simple-markdown-table"

    def get_pipe(self, llmserve: LLMService | None = None) -> BaseActionListingPipe:
        match self.value:
            case ActionListingPipe.SIMPLE_MARKDOWN_TABLE.value:
                pipe = MarkdownTableActionListingPipe(llmserve)
            case _:
                raise ValueError(f"Unknown pipe name: {self.value}")
        return RetryPipeWrapper(pipe)
        # TODO: remove comment when ready
        # return pipe
