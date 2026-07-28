import re
from abc import ABC, abstractmethod
from typing import Any, ClassVar

from notte_core.actions import InteractionAction
from notte_core.browser.snapshot import BrowserSnapshot
from notte_core.common.logging import logger
from notte_core.errors.llm import (
    ContextSizeTooLargeError,
    LLMnoOutputCompletionError,
    LLMParsingError,
)
from notte_core.errors.provider import ContextWindowExceededError
from notte_llm.service import LLMService
from notte_llm.tracer import LlmParsingErrorFileTracer
from typing_extensions import override

from notte_browser.tagging.type import PossibleAction, PossibleActionSpace

_CONTEXT_SIZE_ERROR_MESSAGE = "Please reduce the length of the messages or completions"
_CONTEXT_SIZE_PATTERN = re.compile(r"Current length is (\d+) while limit is (\d+)")


def _context_size_error(error: Exception) -> ContextSizeTooLargeError | ContextWindowExceededError | None:
    if isinstance(error, (ContextSizeTooLargeError, ContextWindowExceededError)):
        return error

    message = str(error)
    if _CONTEXT_SIZE_ERROR_MESSAGE not in message:
        return None

    match = _CONTEXT_SIZE_PATTERN.search(message)
    size = int(match.group(1)) if match is not None else None
    max_size = int(match.group(2)) if match is not None else None
    return ContextSizeTooLargeError(size=size, max_size=max_size)


class BaseActionListingPipe(ABC):
    def __init__(self, llmserve: LLMService) -> None:
        self.llmserve: LLMService = llmserve

    @abstractmethod
    async def forward(
        self, snapshot: BrowserSnapshot, previous_action_list: list[InteractionAction] | None = None
    ) -> PossibleActionSpace:
        pass

    async def llm_completion(self, prompt_id: str, variables: dict[str, Any]) -> str:
        response = await self.llmserve.completion(prompt_id, variables)
        if response.choices[0].message.content is None:  # type: ignore
            raise LLMnoOutputCompletionError()
        return response.choices[0].message.content  # type: ignore

    @abstractmethod
    async def forward_incremental(
        self,
        snapshot: BrowserSnapshot,
        previous_action_list: list[InteractionAction],
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
    async def forward(
        self, snapshot: BrowserSnapshot, previous_action_list: list[InteractionAction] | None = None
    ) -> PossibleActionSpace:
        errors: list[str] = []
        last_error: Exception | None = None
        for _ in range(self.max_tries):
            try:
                out = await self.pipe.forward(snapshot, previous_action_list)
                self.tracer.trace(
                    status="success",
                    pipe_name=self.pipe.__class__.__name__,
                    nb_retries=len(errors),
                    error_msgs=errors,
                )
                return out
            except Exception as e:
                last_error = e
                context_size_error = _context_size_error(e)
                if context_size_error is not None:
                    # Retrying cannot reduce the prompt, so fail immediately.
                    if context_size_error is e:
                        raise
                    raise context_size_error from e
                if self.verbose:
                    logger.opt(exception=True).debug("Failed to parse action list; retrying")
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
    async def forward_incremental(
        self,
        snapshot: BrowserSnapshot,
        previous_action_list: list[InteractionAction],
    ) -> PossibleActionSpace:
        errors: list[str] = []
        for attempt in range(1, self.max_tries + 1):
            try:
                out = await self.pipe.forward_incremental(snapshot, previous_action_list)
                self.tracer.trace(
                    status="success",
                    pipe_name=self.pipe.__class__.__name__,
                    nb_retries=len(errors),
                    error_msgs=errors,
                )
                return out
            except Exception as e:
                errors.append(str(e))
                context_size_error = _context_size_error(e)
                if self.verbose:
                    next_step = "using the previous action list" if context_size_error is not None else "retrying"
                    logger.opt(exception=True).debug(
                        "Incremental action listing attempt {}/{} failed; {}",
                        attempt,
                        self.max_tries,
                        next_step,
                    )
                if context_size_error is not None:
                    # Incremental listing can safely use its previous result, but
                    # retrying the same oversized prompt would be wasted work.
                    break

        self.tracer.trace(
            status="failure",
            pipe_name=self.pipe.__class__.__name__,
            nb_retries=len(errors),
            error_msgs=errors,
        )
        if self.verbose:
            logger.debug(
                "Incremental action listing failed after {} attempt(s); returning the previous action list",
                len(errors),
            )
        return PossibleActionSpace(
            # TODO: get description from previous action list
            description="",
            actions=[
                PossibleAction(
                    id=act.id,
                    description=act.description,
                    category=act.category,
                    param=act.param,
                )
                for act in previous_action_list
            ],
        )
