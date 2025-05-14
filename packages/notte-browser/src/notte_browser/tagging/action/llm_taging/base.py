import re
from abc import ABC, abstractmethod
from typing import Any, ClassVar

from loguru import logger
from notte_core.actions.percieved import PerceivedAction
from notte_core.browser.snapshot import BrowserSnapshot
from notte_core.common.tracer import LlmParsingErrorFileTracer
from notte_core.errors.llm import (
    ContextSizeTooLargeError,
    LLMnoOutputCompletionError,
    LLMParsingError,
)
from notte_core.llms.service import LLMService
from typing_extensions import override

from notte_browser.tagging.types import PossibleAction, PossibleActionSpace


class BaseActionListingPipe(ABC):
    def __init__(self, llmserve: LLMService) -> None:
        self.llmserve: LLMService = llmserve

    @abstractmethod
    def forward(
        self, snapshot: BrowserSnapshot, previous_action_list: list[PerceivedAction] | None = None
    ) -> PossibleActionSpace:
        pass

    def llm_completion(self, prompt_id: str, variables: dict[str, Any]) -> str:
        response = self.llmserve.completion(prompt_id, variables)
        if response.choices[0].message.content is None:  # type: ignore
            raise LLMnoOutputCompletionError()
        return response.choices[0].message.content  # type: ignore

    @abstractmethod
    def forward_incremental(
        self,
        snapshot: BrowserSnapshot,
        previous_action_list: list[PerceivedAction],
    ) -> PossibleActionSpace:
        """
        This method is used to get the next action list based on the previous action list.

        /!\\ This was designed to only be used in the `forward` method when the previous action list is not empty.
        """
        raise NotImplementedError("forward_incremental")


class RetryPipeWrapper(BaseActionListingPipe):
    tracer: ClassVar[LlmParsingErrorFileTracer] = LlmParsingErrorFileTracer()

    def __init__(self, pipe: BaseActionListingPipe, max_tries: int, verbose: bool = False):
        super().__init__(pipe.llmserve)
        self.pipe: BaseActionListingPipe = pipe
        self.max_tries: int = max_tries
        self.verbose: bool = verbose

    @override
    def forward(
        self, snapshot: BrowserSnapshot, previous_action_list: list[PerceivedAction] | None = None
    ) -> PossibleActionSpace:
        errors: list[str] = []
        last_error: Exception | None = None
        for _ in range(self.max_tries):
            try:
                out = self.pipe.forward(snapshot, previous_action_list)
                self.tracer.trace(
                    status="success",
                    pipe_name=self.pipe.__class__.__name__,
                    nb_retries=len(errors),
                    error_msgs=errors,
                )
                return out
            except Exception as e:
                last_error = e
                if "Please reduce the length of the messages or completions" in str(e):
                    # this is a known error that happens when the context is too long
                    # we should not retry in this case (nothing is going to change)
                    pattern = r"Current length is (\d+) while limit is (\d+)"
                    size: int | None = None
                    max_size: int | None = None
                    match = re.search(pattern, str(e))
                    if match:
                        size = int(match.group(1))
                        max_size = int(match.group(2))
                    else:
                        if self.verbose:
                            logger.error(
                                f"Failed to parse context size from error message: {str(e)}. Please fix this ASAP."
                            )
                        raise ContextSizeTooLargeError(size=size, max_size=max_size) from e
                if self.verbose:
                    logger.warning(f"failed to parse action list but retrying. Start of error msg: {str(e)[:200]}...")
                errors.append(str(e))
        self.tracer.trace(
            status="failure",
            pipe_name=self.pipe.__class__.__name__,
            nb_retries=len(errors),
            error_msgs=errors,
        )
        raise LLMParsingError(
            context=f"Action listing failed after {self.max_tries} tries with errors: {errors}"
        ) from last_error

    @override
    def forward_incremental(
        self,
        snapshot: BrowserSnapshot,
        previous_action_list: list[PerceivedAction],
    ) -> PossibleActionSpace:
        for _ in range(self.max_tries):
            try:
                return self.pipe.forward_incremental(snapshot, previous_action_list)
            except Exception:
                pass
        if self.verbose:
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
