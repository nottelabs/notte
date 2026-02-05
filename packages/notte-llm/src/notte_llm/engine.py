from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Literal, cast

import litellm
from litellm import (
    AllMessageValues,
    ChatCompletionUserMessage,
)
from litellm.exceptions import (
    APIError,
    AuthenticationError,
    BadRequestError,
    NotFoundError,
    RateLimitError,
)
from litellm.exceptions import (
    ContextWindowExceededError as LiteLLMContextWindowExceededError,
)
from litellm.files.main import ModelResponse  # pyright: ignore [reportMissingTypeStubs]
from notte_core.common.config import ENABLE_OPENROUTER, LlmModel, config
from notte_core.common.logging import logger
from notte_core.errors.base import NotteBaseError
from notte_core.errors.llm import LLmModelOverloadedError, LLMParsingError
from notte_core.errors.provider import (
    ContextWindowExceededError,
    InsufficentCreditsError,
    InvalidAPIKeyError,
    InvalidJsonResponseForStructuredOutput,
    LLMProviderError,
    MissingAPIKeyForModel,
    ModelDoesNotSupportImageError,
    ModelNotFoundError,
)
from notte_core.errors.provider import RateLimitError as NotteRateLimitError
from notte_core.profiling import profiler
from pydantic import BaseModel, ValidationError, create_model

from notte_llm.logging import trace_llm_usage
from notte_llm.tracer import LlmTracer, LlmUsageFileTracer
from notte_llm.types import TResponseFormat


def fix_schema_for_gemini(schema: dict[str, Any]) -> dict[str, Any]:
    """
    Convert a Pydantic JSON schema to Gemini-compatible format.

    Courtesy of https://github.com/browser-use/browser-use

    Gemini doesn't support:
    - $ref/$defs (JSON Schema references) - must be inlined
    - additionalProperties
    - default values in schema
    - Empty object properties (must have at least one property)
    """
    import copy

    # Step 1: Resolve all $ref references by inlining definitions
    defs: dict[str, Any] = schema.get("$defs", {})

    def resolve_refs(obj: Any) -> Any:
        if isinstance(obj, dict):
            obj_dict = cast(dict[str, Any], obj)
            if "$ref" in obj_dict:
                ref: str = str(obj_dict["$ref"])
                ref_name: str = ref.split("/")[-1]  # "#/$defs/MyType" -> "MyType"
                if ref_name in defs:
                    # Replace reference with actual definition (deep copy to avoid mutation)
                    resolved: dict[str, Any] = copy.deepcopy(defs[ref_name])
                    # Merge any sibling properties (except $ref)
                    for key, value in obj_dict.items():
                        if key != "$ref":
                            resolved[key] = value
                    return resolve_refs(resolved)  # Recurse in case definition has refs
                return cast(dict[str, Any], obj)
            else:
                result: dict[str, Any] = {k: resolve_refs(v) for k, v in obj_dict.items()}
                return result
        elif isinstance(obj, list):
            obj_list = cast(list[Any], obj)
            return [resolve_refs(item) for item in obj_list]
        return obj

    schema = resolve_refs(schema)
    # Remove $defs from resolved schema (now inlined)
    schema.pop("$defs", None)

    # Step 2: Remove unsupported properties and handle edge cases
    def clean_schema(obj: Any, parent_key: str | None = None) -> Any:
        if isinstance(obj, dict):
            obj_dict = cast(dict[str, Any], obj)
            cleaned: dict[str, Any] = {}
            for key, value in obj_dict.items():
                # Skip keys that Gemini doesn't support
                # Note: 'title' is kept as Gemini handles it fine and it's useful for descriptions
                if key in ["additionalProperties", "default"]:
                    continue

                cleaned_value = clean_schema(value, parent_key=key)

                # Handle empty object properties - Gemini rejects these
                if (
                    key == "properties"
                    and isinstance(cleaned_value, dict)
                    and len(cast(dict[str, Any], cleaned_value)) == 0
                    and obj_dict.get("type") == "object"
                ):
                    # Add a placeholder property so Gemini doesn't error
                    cleaned["properties"] = {"_placeholder": {"type": "string"}}
                else:
                    cleaned[key] = cleaned_value

            return cleaned
        elif isinstance(obj, list):
            obj_list = cast(list[Any], obj)
            return [clean_schema(item, parent_key=parent_key) for item in obj_list]
        return obj

    return clean_schema(schema)


def is_gemini_model(model: str) -> bool:
    """Check if the model is a Gemini model that needs schema transformation."""
    model_lower = model.lower()
    return "gemini" in model_lower or "vertex_ai" in model_lower


class LLMEngine:
    PREFIXES: list[str] = ['{"json":', '{"additionalProperties":']  # LLM Response Prefixes

    def __init__(
        self,
        model: str | None = None,
        tracer: LlmTracer | None = None,
        nb_retries_structured_output: int = config.nb_retries_structured_output,
        verbose: bool = False,
    ):
        self.model: str = model or LlmModel.default()
        self.sc: StructuredContent = StructuredContent(inner_tag="json", fail_if_inner_tag=False)

        if tracer is None:
            tracer = LlmUsageFileTracer()

        self.tracer: LlmTracer = tracer
        self.completion = trace_llm_usage(tracer=self.tracer)(self.completion)  # pyright: ignore [reportAttributeAccessIssue]
        self.nb_retries_structured_output: int = nb_retries_structured_output
        self.verbose: bool = verbose

    def context_length(self) -> int:
        return LlmModel.get_provider(self.model).context_length

    @profiler.profiled(service_name="llm")
    async def structured_completion(
        self,
        messages: list[AllMessageValues],
        response_format: type[TResponseFormat],
        model: str | None = None,
        use_strict_response_format: bool = True,
    ) -> TResponseFormat:
        tries = self.nb_retries_structured_output + 1
        content = None
        effective_model = model or self.model

        litellm_response_format: dict[str, Any] | type[BaseModel] = dict(type="json_object")
        if use_strict_response_format:
            # For Gemini models, transform the schema to be compatible
            # Gemini doesn't support $ref/$defs, additionalProperties, etc.
            if is_gemini_model(effective_model):
                raw_schema = response_format.model_json_schema()
                litellm_response_format = fix_schema_for_gemini(raw_schema)
            else:
                litellm_response_format = response_format

        raised_exc = None

        while tries > 0:
            tries -= 1
            try:
                content = (
                    await self.single_completion(messages, model, response_format=litellm_response_format) or ""
                ).strip()
            except InvalidJsonResponseForStructuredOutput as e:
                if use_strict_response_format:
                    # fallback to non-strict response format
                    litellm_response_format = dict(type="json_object")
                    use_strict_response_format = False
                    continue
                raised_exc = e
                raise e
            except NotteBaseError as e:
                raised_exc = e
                raise e

            except Exception as e:
                raised_exc = e
                raise e
            content = self.sc.extract(content).strip()

            if "```json" in content:
                # extract content from JSON code blocks
                content = self.sc.extract(content).strip()
            elif content.startswith(LLMEngine.PREFIXES[0]):
                content = content[len(LLMEngine.PREFIXES[0]) : -1].strip()
            elif content.startswith(LLMEngine.PREFIXES[1]):
                content = content[len(LLMEngine.PREFIXES[1]) : -1].strip()
            elif not content.startswith("{") or not content.endswith("}"):
                messages.append(
                    ChatCompletionUserMessage(
                        role="user",
                        content="Invalid LLM response. JSON code blocks or JSON object expected, but content does not start with curly brackets. Retrying",
                    )
                )
                continue
            try:
                return response_format.model_validate_json(content)
            except ValidationError as e:
                error_details = e.errors()
                messages.append(
                    ChatCompletionUserMessage(
                        role="user",
                        content=f"Error parsing LLM response: {error_details}, retrying",
                    )
                )
                raised_exc = e
                logger.error(f"Error parsing LLM response: {error_details}, retrying")
                continue

        error_string = (
            f"Error parsing LLM response into Structured Output (type: {response_format}). Content: \n\n{content}\n\n"
        )
        raise LLMParsingError(error_string) from raised_exc

    @profiler.profiled(service_name="llm")
    async def single_completion(
        self,
        messages: list[AllMessageValues],
        model: str | None = None,
        temperature: float = config.temperature,
        response_format: dict[str, str] | type[BaseModel] | None = None,
    ) -> str | None:
        model = model or self.model
        response = await self.completion(
            messages,
            model=model,
            temperature=temperature,
            n=1,
            response_format=response_format,
        )
        return response.choices[0].message.content  # pyright: ignore [reportUnknownVariableType, reportUnknownMemberType, reportAttributeAccessIssue]

    def _get_model(self, model: str | None) -> str:
        model = model or self.model
        if ENABLE_OPENROUTER and not model.startswith("openrouter/"):
            return f"openrouter/{model}"
        return model

    @profiler.profiled(service_name="llm")
    async def completion(
        self,
        messages: list[AllMessageValues],
        model: str | None = None,
        temperature: float = config.temperature,
        response_format: dict[str, str] | type[BaseModel] | None = None,
        n: int = 1,
    ) -> ModelResponse:
        model = self._get_model(model)
        # Apply model-specific temperature overrides
        temperature = LlmModel.get_temperature(model, temperature)
        try:
            response = await litellm.acompletion(  # pyright: ignore [reportUnknownMemberType]
                model,
                messages,
                temperature=temperature,
                n=n,
                response_format=response_format,
                max_completion_tokens=8192,
                drop_params=True,
            )
            # Cast to ModelResponse since we know it's not streaming in this case
            return cast(ModelResponse, response)

        except NotFoundError as e:
            raise ModelNotFoundError(model) from e
        except RateLimitError:
            logger.opt(exception=True).error(
                f"Rate limit exceeded for model {model}. You should wait a few seconds before retrying..."
            )
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
            if "Missing API Key" in str(e):
                raise MissingAPIKeyForModel(model) from e
            if "Input should be a valid string" in str(e):
                raise ModelDoesNotSupportImageError(model) from e
            if "Invalid JSON" in str(e):
                raise InvalidJsonResponseForStructuredOutput(model, error_msg=e.message) from e
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
            logger.debug(f"Error generating response: {str(e)}")
            logger.exception("Full traceback:")
            if "credit balance is too low" in str(e):
                raise InsufficentCreditsError() from e
            if "model is overloaded" in str(e):
                raise LLmModelOverloadedError(model) from e
            raise LLMProviderError(
                dev_message=f"Unexpected error from LLM provider: {str(e)}",
                user_message="An unexpected error occurred while processing your request.",
                should_retry_later=True,
                agent_message=None,
            ) from e

    async def choice(self, query: str, choices: list[str] | set[str]) -> str:
        """
        Use LLM to choose the most appropriate answer from the given list of choices.

        Example:
            >>> llm = LLMEngine(model="gpt-4o-mini")
            >>> llm.choice("What is the capital of France?", ["Paris", "London", "Berlin"])
            "Paris"

        Args:
            query: The user query to choose the most appropriate answer from the given list of choices.
            choices: The list of choices to choose the most appropriate answer from.

        Returns:
            The most appropriate answer from the given list of choices.
        """
        if query in choices:
            logger.info(f"User query {query} is already in choices")
            return query
        if len(choices) == 1:
            choice = choices[0] if isinstance(choices, list) else next(iter(choices))
            logger.info(f"Only one choice available: {choice}")
            return choice
        logger.info(f"User query '{query}' is not in choices. Using LLM to choose from: '{choices}'")

        def create_choice_model(types: Iterable[str]) -> type[BaseModel]:
            # Create a Literal type with all possible vehicle models
            ModelType = Literal[tuple(types)]

            # Create the dynamic Choice model
            Choice = create_model(
                "Choice",
                choice=(ModelType, ...),  # Required field with type annotation
                __base__=BaseModel,
            )
            return Choice

        messages: list[AllMessageValues] = [
            {
                "role": "user",
                "content": f"""
                Based on the following user query: {query}, I need you to select the most appropriate answer from the following list:
                {choices}
                If you don't know the answer, make a educated guess.
                """,
            }
        ]
        choice = await self.structured_completion(messages=messages, response_format=create_choice_model(choices))
        return choice.choice  # type: ignore


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
