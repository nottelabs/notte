from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from typing import Any, cast

import httpx
from json_repair import repair_json
from notte_core.errors import (
    ContextWindowExceededError,
    InsufficentCreditsError,
    InvalidAPIKeyError,
    InvalidJsonResponseForStructuredOutput,
    LLMParsingError,
    LLMProviderError,
    ModelNotFoundError,
    UnsupportedResponseSchemaError,
)
from notte_core.errors import RateLimitError as NotteRateLimitError
from notte_core.logging import logger
from notte_core.profiling import profiler
from notte_core.schema import TResponseFormat
from pydantic import BaseModel, ValidationError

from notte_llm.config import LlmSettings
from notte_llm.prompt import Message


class _UnsupportedStrictSchema(ValueError):
    """The strict subset cannot preserve the caller's data contract."""


def _resolve_schema_refs(schema: dict[str, Any]) -> dict[str, Any]:
    """Inline all $ref/$defs references in a JSON Schema (shared utility)."""
    import copy

    defs: dict[str, Any] = schema.get("$defs", {})

    def resolve_refs(obj: Any, active_refs: tuple[str, ...] = ()) -> Any:
        if isinstance(obj, dict):
            obj_dict = cast(dict[str, Any], obj)
            if "$ref" in obj_dict:
                ref_name = str(obj_dict["$ref"]).split("/")[-1]
                if ref_name in active_refs:
                    raise _UnsupportedStrictSchema("Recursive references require the schema-in-prompt path")
                if ref_name in defs:
                    resolved = copy.deepcopy(defs[ref_name])
                    for key, value in obj_dict.items():
                        if key != "$ref":
                            resolved[key] = value
                    return resolve_refs(resolved, (*active_refs, ref_name))
                raise _UnsupportedStrictSchema("Unresolved references require the schema-in-prompt path")
            return {k: resolve_refs(v, active_refs) for k, v in obj_dict.items()}
        elif isinstance(obj, list):
            return [resolve_refs(item, active_refs) for item in cast(list[Any], obj)]
        return obj

    resolved = resolve_refs(schema)
    resolved.pop("$defs", None)
    return resolved


def is_schema_rejection(message: str) -> bool:
    """Recognize schema/format rejections across compatible endpoints."""
    return (
        re.search(r"json.?schema|response.?format|output_format\.schema|union types", message, re.IGNORECASE)
        is not None
    )


def fix_schema_for_openai(schema: dict[str, Any]) -> dict[str, Any]:
    """
    Convert a Pydantic JSON schema to OpenAI-compatible structured output format.

    OpenAI structured output doesn't support:
    - Certain formats like "password", "writeOnly"
    - $ref/$defs (must be inlined for strict mode)

    Returns the schema wrapped in OpenAI's json_schema response_format structure.
    """
    # Extract schema name (title) before processing
    # OpenAI requires name to match ^[a-zA-Z0-9_-]{1,64}$ so we sanitize and truncate it
    raw_name = schema.get("title", "response")
    schema_name = re.sub(r"[^a-zA-Z0-9_-]", "_", raw_name)[:64]

    # Step 1: Resolve all $ref references by inlining definitions
    schema = _resolve_schema_refs(schema)

    # Step 2: Clean schema for OpenAI strict mode
    # OpenAI structured output only supports a limited subset of JSON Schema keywords.
    # Using a whitelist approach to only keep supported keys.
    # Ref: https://platform.openai.com/docs/guides/structured-outputs
    # Note: "required" is intentionally omitted - we skip it explicitly and regenerate it
    allowed_schema_keys = {
        "type",
        "properties",
        "items",
        "enum",
        "anyOf",
        "allOf",
        "const",
        "description",
        # Note: "title" is intentionally omitted - not in OpenAI's strict-mode supported keywords
        # Note: "additionalProperties" is intentionally omitted - we unconditionally set it to False
        "minItems",
        "maxItems",
        "prefixItems",
    }

    def _expand_property_names(obj_dict: dict[str, Any]) -> dict[str, Any] | None:
        """When an object uses propertyNames + additionalProperties with real type
        info, expand into explicit properties so downstream transforms can handle it."""
        additional = obj_dict.get("additionalProperties")
        pn = obj_dict.get("propertyNames")
        property_names_enum: list[str] | None = None
        if isinstance(pn, dict):
            pn_dict = cast(dict[str, Any], pn)
            property_names_enum = cast(list[str] | None, pn_dict.get("enum"))
        if isinstance(additional, dict) and property_names_enum is not None and obj_dict.get("type") == "object":
            value_schema: dict[str, Any] = additional
            explicit_props: dict[str, Any] = {}
            for prop_name in property_names_enum:
                explicit_props[prop_name] = dict(value_schema)
            # Rebuild without propertyNames/minProperties/additionalProperties
            rebuilt: dict[str, Any] = {}
            for k, v in obj_dict.items():
                if k in ("additionalProperties", "propertyNames", "minProperties"):
                    continue
                rebuilt[k] = v
            # Merge with any pre-existing static properties rather than overwriting
            existing_props = cast(dict[str, Any], rebuilt.get("properties", {}))
            rebuilt["properties"] = {**existing_props, **explicit_props}
            return rebuilt
        return None

    def clean_schema(obj: Any, *, is_properties_map: bool = False) -> Any:
        if isinstance(obj, dict):
            obj_dict = cast(dict[str, Any], obj)

            # Expand propertyNames + additionalProperties pattern into explicit
            # properties before applying the whitelist, otherwise the keys get
            # stripped and the object ends up empty.
            was_expanded = False
            if not is_properties_map:
                expanded = _expand_property_names(obj_dict)
                if expanded is not None:
                    obj_dict = expanded
                    was_expanded = True
                elif obj_dict.get("additionalProperties") is True or isinstance(
                    obj_dict.get("additionalProperties"), dict
                ):
                    raise _UnsupportedStrictSchema("Open-ended dictionaries require the schema-in-prompt path")

            cleaned: dict[str, Any] = {}
            for key, value in obj_dict.items():
                # OpenAI strict mode doesn't support oneOf, convert to anyOf
                # Only apply to schema keywords, not property names
                if not is_properties_map and key == "oneOf":
                    cleaned["anyOf"] = clean_schema(value, is_properties_map=False)
                    continue

                # Skip original `required` - we'll regenerate it from properties
                # Only apply to schema keywords, not property names
                if not is_properties_map and key == "required":
                    continue

                # If we're inside a "properties" map, keep all keys (they're property names)
                # Only apply the whitelist to JSON Schema keywords
                if not is_properties_map and key not in allowed_schema_keys:
                    continue

                # Recursively clean - only pass is_properties_map=True when we're at a schema-level
                # "properties" key (not when a property is named "properties")
                if isinstance(value, (dict, list)):
                    cleaned[key] = clean_schema(
                        value, is_properties_map=(not is_properties_map and key == "properties")
                    )
                else:
                    cleaned[key] = value

            # OpenAI strict mode requires:
            # 1. additionalProperties: false on all objects
            # 2. properties must be defined (even if empty)
            # 3. required must include exactly all property keys
            if not is_properties_map and ("properties" in cleaned or cleaned.get("type") == "object"):
                cleaned["additionalProperties"] = False
                # Ensure properties exists (OpenAI requires it for objects)
                if "properties" not in cleaned:
                    cleaned["properties"] = {}
                # For expanded propertyNames objects, make properties optional via
                # nullable anyOf — OpenAI strict mode requires ALL properties in
                # required, so we can't use required=[] with non-empty properties.
                if was_expanded:
                    props = cast(dict[str, Any], cleaned["properties"])
                    for prop_key in list(props.keys()):
                        original: dict[str, Any] = cast(dict[str, Any], props[prop_key])
                        if "anyOf" in original:
                            branches: list[Any] = list(original["anyOf"]) + [{"type": "null"}]
                            props[prop_key] = {"anyOf": branches}
                        else:
                            props[prop_key] = {"anyOf": [original, {"type": "null"}]}
                cleaned["required"] = list(cast(dict[str, Any], cleaned["properties"]).keys())

            return cleaned
        elif isinstance(obj, list):
            obj_list = cast(list[Any], obj)
            return [clean_schema(item, is_properties_map=False) for item in obj_list]
        return obj

    cleaned_schema = clean_schema(schema)

    # Step 3: Wrap in OpenAI's json_schema response_format structure
    return {
        "type": "json_schema",
        "json_schema": {
            "name": schema_name,
            "strict": True,
            "schema": cleaned_schema,
        },
    }


# Provider errors that usually clear on their own (overloaded model, rate limit, dropped
# connection, timeout). completion() retries them after these delays before giving up.
_TRANSIENT_RETRY_DELAYS_SECONDS = (2.0, 5.0)

# OpenRouter tries these, in order, when the requested model errors (for example a 503 while it
# is overloaded). Both support the structured outputs the agent relies on.
OPENROUTER_FALLBACK_MODELS = ("google/gemini-2.5-flash", "openai/gpt-4.1-mini")


class LLMEngine:
    PREFIXES: list[str] = ['{"json":', '{"additionalProperties":']  # LLM Response Prefixes

    def __init__(
        self,
        model: str | None = None,
        nb_retries_structured_output: int | None = None,
        verbose: bool = False,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        provider_order: list[str] | None = None,
        reasoning: dict[str, Any] | None = None,
    ):
        self.settings: LlmSettings = LlmSettings.from_env(model=model)
        self.model: str = self.settings.model
        self.transport: httpx.AsyncBaseTransport | None = transport
        self.provider_order: list[str] | None = provider_order
        self.reasoning: dict[str, Any] | None = reasoning
        self.sc: StructuredContent = StructuredContent(inner_tag="json", fail_if_inner_tag=False)

        if nb_retries_structured_output is None:
            nb_retries_structured_output = self.settings.nb_retries_structured_output
        self.nb_retries_structured_output: int = nb_retries_structured_output
        self.verbose: bool = verbose

    @profiler.profiled(service_name="llm")
    async def structured_completion(
        self,
        messages: list[Message],
        response_format: type[TResponseFormat],
        model: str | None = None,
        use_strict_response_format: bool = True,
    ) -> TResponseFormat:
        # Retries add feedback messages: keep them out of the caller's list.
        messages = list(messages)
        tries = self.nb_retries_structured_output + 1
        content = None
        effective_model = model or self.model

        request_format: dict[str, Any] | None = dict(type="json_object")
        raw_schema = response_format.model_json_schema()
        if use_strict_response_format:
            try:
                request_format = fix_schema_for_openai(raw_schema)
            except _UnsupportedStrictSchema as e:
                logger.debug(f"Using schema in prompt for model {effective_model}: {e}")
                use_strict_response_format = False

        raised_exc = None
        schema_in_messages = False

        while tries > 0:
            if not use_strict_response_format and not schema_in_messages:
                # json_object constrains syntax only. Preserve the answer contract when
                # strict mode is unavailable.
                messages.append(
                    Message(
                        role="user",
                        content=f"Return a JSON object matching this JSON schema: {json.dumps(raw_schema)}",
                    )
                )
                schema_in_messages = True
            tries -= 1
            try:
                content = (await self.single_completion(messages, model, response_format=request_format) or "").strip()
            except (InvalidJsonResponseForStructuredOutput, UnsupportedResponseSchemaError, ModelNotFoundError) as e:
                if use_strict_response_format:
                    logger.warning(f"Model {effective_model} rejected strict output; retrying with json_object")
                    request_format = {"type": "json_object"}
                    use_strict_response_format = False
                    tries += 1  # Format negotiation does not consume a parsing retry.
                    continue
                if isinstance(e, UnsupportedResponseSchemaError) and request_format is not None:
                    # Some compatibility layers support strict schemas but reject json_object.
                    # The schema already in the prompt still defines the answer contract.
                    logger.warning(f"Model {effective_model} rejected json_object; retrying with schema in prompt")
                    request_format = None
                    tries += 1
                    continue
                raise
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
                    Message(
                        role="user",
                        content="Invalid LLM response. JSON code blocks or JSON object expected, but content does not start with curly brackets. Retrying",
                    )
                )
                continue
            try:
                return response_format.model_validate_json(content)
            except ValidationError as e:
                error_details = e.errors()
                is_json_invalid = any(err.get("type") == "json_invalid" for err in error_details)

                if is_json_invalid:
                    repaired = self._try_repair_json(content, response_format)
                    if repaired is not None:
                        return repaired

                # Build a more helpful retry message for JSON issues
                if is_json_invalid:
                    retry_content = (
                        f"Error parsing LLM response: {error_details}. "
                        "Your response contained invalid JSON. Common causes:\n"
                        "- Trailing characters after the closing }}. Do NOT wrap the JSON in extra quotes.\n"
                        "- Unescaped double quotes inside string values (e.g. in JavaScript code). "
                        'All double quotes within JSON string values MUST be escaped as \\"\n'
                        "Please output ONLY the raw JSON object, nothing else."
                    )
                else:
                    retry_content = f"Error parsing LLM response: {error_details}, retrying"

                messages.append(
                    Message(
                        role="user",
                        content=retry_content,
                    )
                )
                raised_exc = e
                logger.error(f"Error parsing LLM response: {error_details}, retrying")
                continue

        error_string = (
            f"Error parsing LLM response into Structured Output (type: {response_format}). Content: \n\n{content}\n\n"
        )
        raise LLMParsingError(error_string) from raised_exc

    @staticmethod
    def _try_repair_json(
        content: str,
        response_format: type[TResponseFormat],
    ) -> TResponseFormat | None:
        """Attempt to recover a valid response from malformed JSON using ``json_repair``.

        Handles trailing characters, unescaped quotes inside string values,
        missing commas, unclosed brackets, and other common LLM output issues.

        Returns the validated response or ``None`` if recovery failed.
        """
        try:
            repaired_str = repair_json(content, return_objects=False)
            result = response_format.model_validate_json(repaired_str)
            logger.debug("Recovered malformed JSON via json_repair")
            return result
        except Exception:
            return None

    @profiler.profiled(service_name="llm")
    async def single_completion(
        self,
        messages: list[Message],
        model: str | None = None,
        temperature: float | None = None,
        response_format: dict[str, Any] | type[BaseModel] | None = None,
    ) -> str | None:
        response = await self.completion(
            messages, model=model, temperature=temperature, response_format=response_format
        )
        choices = response.get("choices", [])
        if not choices:
            return None
        content = choices[0]["message"].get("content")
        if content is not None and not isinstance(content, str):
            raise LLMProviderError(
                dev_message=f"Invalid message content from model {model or self.model}",
                user_message="The LLM provider returned an invalid response.",
                agent_message=None,
                should_retry_later=True,
            )
        return cast(str | None, content)

    def _get_extra_body(self, model: str | None) -> dict[str, Any]:
        if not self.settings.is_openrouter:
            return {}
        requested = model or self.model
        body: dict[str, Any] = {
            "models": [requested, *(fallback for fallback in OPENROUTER_FALLBACK_MODELS if fallback != requested)]
        }
        if self.provider_order is not None:
            body["provider"] = {"order": self.provider_order, "allow_fallbacks": True}
        if self.reasoning is not None:
            body["reasoning"] = self.reasoning
        return body

    def _raise_provider_error(self, status: int, message: str, model: str) -> None:
        if status in (401, 403):
            raise InvalidAPIKeyError(provider=model)
        if status == 404:
            raise ModelNotFoundError(model)
        if status == 429:
            raise NotteRateLimitError(provider=model)
        if re.search(
            r"context[_ -]?(length|window)|maximum context|too many (input )?tokens|prompt is too long|current length is",
            message,
            re.IGNORECASE,
        ):
            sizes = re.search(r"Current length is (\d+) while limit is (\d+)", message)
            raise ContextWindowExceededError(
                provider=model,
                current_size=int(sizes[1]) if sizes else None,
                max_size=int(sizes[2]) if sizes else None,
            )
        if status in (400, 422) and is_schema_rejection(message):
            raise UnsupportedResponseSchemaError(model, error_msg=message)
        if status == 400 and "invalid json" in message.lower():
            raise InvalidJsonResponseForStructuredOutput(model, error_msg=message)
        if status == 402 or "insufficient balance" in message.lower() or "credit balance is too low" in message.lower():
            raise InsufficentCreditsError()
        raise LLMProviderError(
            dev_message=f"HTTP {status} from LLM model {model}: {message}",
            user_message="The LLM provider could not process the request.",
            agent_message=None,
            should_retry_later=status >= 500 or status in (408, 429),
        )

    @profiler.profiled(service_name="llm")
    async def completion(
        self,
        messages: list[Message],
        model: str | None = None,
        temperature: float | None = None,
        response_format: dict[str, Any] | type[BaseModel] | None = None,
        n: int = 1,
    ) -> dict[str, Any]:
        model = model or self.model
        key = self.settings.require_api_key()
        if isinstance(response_format, type):
            response_format = fix_schema_for_openai(response_format.model_json_schema())
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": self.settings.temperature if temperature is None else temperature,
            "max_completion_tokens": 8192,
            "n": n,
            **self._get_extra_body(model),
        }
        if response_format is not None:
            body["response_format"] = response_format
        async with httpx.AsyncClient(transport=self.transport) as client:
            for attempt, retry_delay in enumerate((*_TRANSIENT_RETRY_DELAYS_SECONDS, None), start=1):
                try:
                    response = await client.post(
                        f"{self.settings.base_url}/chat/completions",
                        headers={"Authorization": f"Bearer {key}"},
                        json=body,
                        timeout=60.0,
                    )
                    status = response.status_code
                    try:
                        payload: Any = response.json()
                    except ValueError:
                        payload = None
                    # Compatible gateways can also embed a provider error in an HTTP 200 body.
                    if isinstance(payload, dict) and "error" in payload and status < 400:
                        error = cast(dict[str, Any], payload).get("error")
                        status = cast(dict[str, Any], error).get("code", 502) if isinstance(error, dict) else 502
                        if not isinstance(status, int) or not 400 <= status <= 599:
                            status = 502
                    if status == 408 or status == 429 or status >= 500:
                        if retry_delay is not None:
                            logger.warning(f"Transient HTTP {status} from {model} (attempt {attempt}); retrying")
                            await asyncio.sleep(retry_delay)
                            continue
                    if status >= 400:
                        # Never propagate the request or its Authorization header in an error.
                        message = response.text.replace(key, "[REDACTED]")
                        self._raise_provider_error(status, message, model)
                    if not isinstance(payload, dict) or not isinstance(
                        cast(dict[str, Any], payload).get("choices"), list
                    ):
                        raise LLMProviderError(
                            dev_message=f"Invalid Chat Completions response from model {model}",
                            user_message="The LLM provider returned an invalid response.",
                            agent_message=None,
                            should_retry_later=True,
                        )
                    choices = cast(list[Any], cast(dict[str, Any], payload)["choices"])
                    if any(
                        not isinstance(choice, dict)
                        or not isinstance(cast(dict[str, Any], choice).get("message"), dict)
                        for choice in choices
                    ):
                        raise LLMProviderError(
                            dev_message=f"Invalid Chat Completions choices from model {model}",
                            user_message="The LLM provider returned an invalid response.",
                            agent_message=None,
                            should_retry_later=True,
                        )
                    return cast(dict[str, Any], payload)
                except (httpx.TimeoutException, httpx.TransportError) as e:
                    if retry_delay is not None:
                        logger.warning(f"Transient {type(e).__name__} from {model} (attempt {attempt}); retrying")
                        await asyncio.sleep(retry_delay)
                        continue
                    raise LLMProviderError(
                        dev_message=f"LLM request to {model} failed after retries ({type(e).__name__})",
                        user_message="The LLM provider did not respond in time or could not be reached.",
                        agent_message=None,
                        should_retry_later=True,
                    ) from None
        raise AssertionError("unreachable: the last attempt returns or raises")


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
