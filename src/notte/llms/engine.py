import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, TypeVar, cast

import litellm
from litellm import (
    AllMessageValues,
    ChatCompletionUserMessage,
)
from litellm.exceptions import (
    APIError,
    AuthenticationError,
    BadRequestError,
    RateLimitError,
)
from litellm.exceptions import (
    ContextWindowExceededError as LiteLLMContextWindowExceededError,
)
from litellm.files.main import ModelResponse  # type: ignore[reportPrivateImportUsage]
from loguru import logger
from pydantic import BaseModel, ValidationError

from notte.common.tracer import LlmTracer, LlmUsageFileTracer
from notte.errors.llm import LLMParsingError
from notte.errors.provider import (
    ContextWindowExceededError,
    InsufficentCreditsError,
    InvalidAPIKeyError,
    LLMProviderError,
    ModelDoesNotSupportImageError,
)
from notte.errors.provider import RateLimitError as NotteRateLimitError
from notte.llms.instructor_integration import validate_structured_output
from notte.llms.logging import trace_llm_usage


class LlmModel(StrEnum):
    openai = "openai/gpt-4o"
    gemini = "gemini/gemini-2.0-flash"
    cerebras = "cerebras/llama-3.3-70b"
    groq = "groq/llama-3.3-70b-versatile"

    @staticmethod
    def default() -> str:
        return LlmModel.gemini


TResponseFormat = TypeVar("TResponseFormat", bound=BaseModel)


class LLMEngine:
    def __init__(self, model: str | None = None, tracer: LlmTracer | None = None, structured_output_retries: int = 0):
        self.model: str = model or LlmModel.default()
        self.sc: StructuredContent = StructuredContent(inner_tag="json", fail_if_inner_tag=False)

        if tracer is None:
            tracer = LlmUsageFileTracer()

        self.tracer: LlmTracer = tracer
        self.completion = trace_llm_usage(tracer=self.tracer)(self.completion)
        self.structured_output_retries: int = structured_output_retries

    def structured_completion(
        self,
        messages: list[AllMessageValues],
        response_format: type[TResponseFormat],
        model: str | None = None,
    ) -> TResponseFormat:
        tries = self.structured_output_retries + 1
        content = None
        last_error = None

        while tries > 0:
            tries -= 1
            content = self.single_completion(messages, model, response_format=dict(type="json_object")).strip()
            content = self.sc.extract(content).strip()
            logger.info(f"LLM response: \n{content}")
            if "```json" in content:
                # extract content from JSON code blocks
                content = self.sc.extract(content).strip()
            elif not content.startswith("{") or not content.endswith("}"):
                messages.append(
                    ChatCompletionUserMessage(
                        role="user",
                        content=f"Invalid LLM response. JSON code blocks or JSON object expected, got: {content}. Retrying",
                    )
                )
                continue

            try:
                # Use our enhanced validation with retries
                # Cast messages to the expected type for validate_structured_output
                typed_messages = cast(Sequence[dict[str, Any]], messages)
                return validate_structured_output(
                    json_str=content,
                    response_model=response_format,
                    max_retries=self.structured_output_retries,
                    llm_completion_fn=lambda msgs, fmt: self.single_completion(
                        cast(list[AllMessageValues], msgs), model, response_format=fmt
                    ),
                    messages=typed_messages,
                )
            except ValidationError as e:
                last_error = e
                error_msg = str(e)
                messages.append(
                    ChatCompletionUserMessage(
                        role="user",
                        content=f"Invalid LLM response. Validation error: {error_msg}. Retrying",
                    )
                )
            except Exception as e:
                last_error = e
                error_msg = str(e)
                messages.append(
                    ChatCompletionUserMessage(
                        role="user",
                        content=f"Invalid LLM response. Error: {error_msg}. Retrying",
                    )
                )

        # we've exhausted the retries
        if content is not None:
            logger.error(f"Failed to parse LLM response after {self.structured_output_retries + 1} tries: {content}")
            if last_error:
                logger.error(f"Last error: {last_error}")

            # Make one final attempt with direct validation
            try:
                return response_format.model_validate_json(content)
            except ValidationError as e:
                raise LLMParsingError(f"Failed to parse LLM response: {e}")

        raise LLMParsingError("Failed to get valid LLM response")

    def single_completion(
        self,
        messages: list[AllMessageValues],
        model: str | None = None,
        temperature: float = 0.0,
        response_format: dict[str, str] | None = None,
    ) -> str:
        model = model or self.model
        response = self.completion(
            messages,
            model=model,
            temperature=temperature,
            n=1,
            response_format=response_format,
        )
        return response.choices[0].message.content  # type: ignore

    def completion(
        self,
        messages: list[AllMessageValues],
        model: str | None = None,
        temperature: float = 0.0,
        response_format: dict[str, str] | None = None,
        n: int = 1,
    ) -> ModelResponse:
        model = model or self.model
        try:
            response = litellm.completion(  # type: ignore[arg-type]
                model,
                messages,
                temperature=temperature,
                n=n,
                response_format=response_format,
            )
            # Cast to ModelResponse since we know it's not streaming in this case
            return cast(ModelResponse, response)

        except RateLimitError:
            raise NotteRateLimitError(provider=model)
        except AuthenticationError:
            raise InvalidAPIKeyError(provider=model)
        except LiteLLMContextWindowExceededError as e:
            # Try to extract size information from error message
            current_size = None
            max_size = None
            pattern = r"Current length is (\d+) while limit is (\d+)"
            match = re.search(pattern, str(e))
            if match:
                current_size = int(match.group(1))
                max_size = int(match.group(2))
            raise ContextWindowExceededError(
                provider=model,
                current_size=current_size,
                max_size=max_size,
            ) from e
        except BadRequestError as e:
            if "Input should be a valid string" in str(e):
                raise ModelDoesNotSupportImageError(model) from e
            raise LLMProviderError(
                dev_message=f"Bad request to provider {model}. {str(e)}",
                user_message="Invalid request parameters to LLM provider.",
                agent_message=None,
                should_retry_later=False,
            ) from e
        except APIError as e:
            raise LLMProviderError(
                dev_message=f"API error from provider {model}. {str(e)}",
                user_message="An unexpected error occurred while processing your request.",
                agent_message=None,
                should_retry_later=True,
            ) from e
        except Exception as e:
            logger.error(f"Error generating response: {str(e)}")
            logger.exception("Full traceback:")
            if "credit balance is too low" in str(e):
                raise InsufficentCreditsError() from e
            raise LLMProviderError(
                dev_message=f"Unexpected error from LLM provider: {str(e)}",
                user_message="An unexpected error occurred while processing your request.",
                should_retry_later=True,
                agent_message=None,
            ) from e


@dataclass
class StructuredContent:
    """Defines how to extract structured content from LLM responses"""

    outer_tag: str | None = None
    inner_tag: str | None = None
    next_outer_tag: str | None = None
    # If True, raise an error if the final tag is not found
    fail_if_final_tag: bool = True
    # If True, raise an error if the inner tag is not found
    fail_if_inner_tag: bool = True
    # If True, raise an error if the next outer tag is not found
    fail_if_next_outer_tag: bool = True

    def extract(
        self,
        text: str,
    ) -> str:
        """Extract content from text based on defined tags

        Parameters:
                text: The text to extract content from

        """
        content = text

        if self.outer_tag:
            pattern = f"<{self.outer_tag}>(.*?)</{self.outer_tag}>"
            match = re.search(pattern, content, re.DOTALL)
            if match:
                # perfect case, we have <outer_tag>...</outer_tag>
                content = match.group(1).strip()
            else:
                splits = text.split(f"<{self.outer_tag}>")
                # In this case, we want to fail if <outer_tag> is not found at least once
                if self.fail_if_final_tag or len(splits) == 1:
                    raise LLMParsingError(f"No content found within <{self.outer_tag}> tags in the response: {text}")
                possible_match = splits[1]
                if (
                    self.next_outer_tag is not None
                    and not self.fail_if_next_outer_tag
                    and f"<{self.next_outer_tag}>" in possible_match
                ):
                    # retry to split by next outer tag
                    splits = possible_match.split(f"<{self.next_outer_tag}>")
                    if len(splits) == 1:
                        raise LLMParsingError(
                            f"Unexpected error <{self.outer_tag}> should be present in the response: {splits}"
                        )
                    possible_match = splits[0].strip()
                # if there is not html tag in `possible_match` then we can safely return it
                if re.search(r"<[^>]*>", possible_match):
                    raise LLMParsingError(f"No content found within <{self.outer_tag}> tags in the response: {text}")
                content = possible_match

        if self.inner_tag:
            pattern = f"```{self.inner_tag}(.*?)```"
            match = re.search(pattern, content, re.DOTALL)
            if match:
                return match.group(1).strip()
            if self.fail_if_inner_tag:
                raise LLMParsingError(f"No content found within ```{self.inner_tag}``` blocks in the response: {text}")
            return content

        return content
