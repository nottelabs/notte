from typing import Any
from unittest.mock import Mock, patch

import pytest
from litellm import BadRequestError, Message, ServiceUnavailableError
from notte_core.errors.base import ErrorConfig
from notte_core.errors.provider import LLMProviderError, UnsupportedResponseSchemaError
from notte_llm.engine import (
    OPENROUTER_FALLBACK_MODELS,
    LLMEngine,
    StructuredContent,
    fix_schema_for_gemini,
    fix_schema_for_openai,
    get_vertex_location,
    is_schema_rejection,
)
from pydantic import BaseModel, create_model


@pytest.fixture
def llm_engine() -> LLMEngine:
    return LLMEngine()


@pytest.mark.asyncio
async def test_completion_success(llm_engine: LLMEngine) -> None:
    messages = [
        Message(role="user", content="Hello"),
    ]
    model = "gpt-3.5-turbo"

    mock_response = Mock()
    mock_response.choices = [Mock(message=Mock(content="Hello there!"))]

    with patch("litellm.acompletion", return_value=mock_response):
        response = await llm_engine.completion(messages=messages, model=model)

        assert response == mock_response
        assert response.choices[0].message.content == "Hello there!"


@pytest.mark.asyncio
async def test_completion_error(llm_engine: LLMEngine) -> None:
    messages = [
        Message(role="user", content="Hello"),
    ]
    model = "gpt-3.5-turbo"

    with ErrorConfig.message_mode("developer"):
        with patch("litellm.acompletion", side_effect=Exception("API Error")):
            with pytest.raises(ValueError) as exc_info:
                _ = await llm_engine.completion(messages=messages, model=model)

            assert "API Error" in str(exc_info.value)


class TestGetVertexLocation:
    @pytest.fixture(autouse=True)
    def _no_configured_location(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("litellm.vertex_location", None)
        monkeypatch.delenv("VERTEXAI_LOCATION", raising=False)
        monkeypatch.delenv("VERTEX_LOCATION", raising=False)

    def test_vertex_gemini_defaults_to_global(self) -> None:
        assert get_vertex_location("vertex_ai/gemini-3.5-flash") == "global"

    def test_env_location_is_respected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("VERTEXAI_LOCATION", "europe-west2")
        assert get_vertex_location("vertex_ai/gemini-3.5-flash") == "europe-west2"

    def test_litellm_location_is_respected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("litellm.vertex_location", "us")
        assert get_vertex_location("vertex_ai/gemini-3.5-flash") == "us"

    @pytest.mark.parametrize(
        "model",
        [
            "gemini/gemini-3.5-flash",
            "openrouter/google/gemini-3.5-flash",
            "vertex_ai/claude-sonnet-4-5",
            "vertex_ai/mistral-large",
            "vertex_ai/meta/llama-3.3-70b-instruct-maas",
            "openai/gpt-4o",
        ],
    )
    def test_other_models_have_no_location(self, model: str) -> None:
        assert get_vertex_location(model) is None


@pytest.mark.asyncio
async def test_completion_passes_global_location_for_vertex_gemini(
    llm_engine: LLMEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("litellm.vertex_location", None)
    monkeypatch.delenv("VERTEXAI_LOCATION", raising=False)
    monkeypatch.delenv("VERTEX_LOCATION", raising=False)
    with patch("litellm.acompletion", return_value=Mock()) as acompletion:
        await llm_engine.completion(
            messages=[Message(role="user", content="Hello")], model="vertex_ai/gemini-3.5-flash"
        )
    assert acompletion.call_args.kwargs["vertex_location"] == "global"


@pytest.mark.asyncio
async def test_completion_omits_location_for_other_models(llm_engine: LLMEngine) -> None:
    with patch("litellm.acompletion", return_value=Mock()) as acompletion:
        await llm_engine.completion(messages=[Message(role="user", content="Hello")], model="gpt-3.5-turbo")
    assert "vertex_location" not in acompletion.call_args.kwargs


@pytest.mark.asyncio
async def test_completion_omits_empty_extra_body(llm_engine: LLMEngine) -> None:
    with patch("litellm.acompletion", return_value=Mock()) as acompletion:
        await llm_engine.completion(messages=[Message(role="user", content="Hello")], model="anthropic/x")
    assert "extra_body" not in acompletion.call_args.kwargs


@pytest.mark.asyncio
async def test_completion_passes_non_empty_extra_body(llm_engine: LLMEngine) -> None:
    extra_body = {"provider": {"order": ["anthropic"], "allow_fallbacks": True}}
    with (
        patch.object(llm_engine, "_get_extra_body", return_value=extra_body),
        patch("litellm.acompletion", return_value=Mock()) as acompletion,
    ):
        await llm_engine.completion(messages=[Message(role="user", content="Hello")], model="anthropic/x")
    assert acompletion.call_args.kwargs["extra_body"] == extra_body


@pytest.mark.asyncio
async def test_completion_maps_groq_gpt_oss_to_groq_model_id(llm_engine: LLMEngine) -> None:
    with (
        patch("notte_llm.engine.enable_openrouter", return_value=False),
        patch("litellm.acompletion", return_value=Mock()) as acompletion,
    ):
        await llm_engine.completion(messages=[Message(role="user", content="Hello")], model="groq/gpt-oss-120b")
    assert acompletion.call_args.args[0] == "groq/openai/gpt-oss-120b"


class TestStructuredContent:
    def test_extract_with_outer_tag(self):
        structure = StructuredContent(outer_tag="response")
        text = "<response>Hello world</response>"
        assert structure.extract(text) == "Hello world"

    def test_extract_with_inner_tag(self):
        structure = StructuredContent(inner_tag="python")
        text = "Some text\n```python\nx = 1\n```\nMore text"
        assert structure.extract(text) == "x = 1"

    def test_extract_with_both_tags(self):
        structure = StructuredContent(outer_tag="response", inner_tag="python")
        text = "<response>\nSome text\n```python\nx = 1\n```\nMore text</response>"
        assert structure.extract(text) == "x = 1"

    def test_extract_missing_outer_tag(self):
        structure = StructuredContent(outer_tag="response")
        text = "Hello world"
        with ErrorConfig.message_mode("developer"):
            with pytest.raises(ValueError) as exc_info:
                structure.extract(text)
        assert "No content found within <response> tags" in str(exc_info.value)

    def test_extract_missing_inner_tag(self):
        structure = StructuredContent(inner_tag="python")
        text = "Some text without code block"
        with ErrorConfig.message_mode("developer"):
            with pytest.raises(ValueError) as exc_info:
                structure.extract(text)
        assert "No content found within ```python``` blocks" in str(exc_info.value)


class TestFixSchemaForGemini:
    """Tests for fix_schema_for_gemini to prevent regressions in schema transformation."""

    def test_strips_boolean_additional_properties(self):
        schema = {
            "type": "object",
            "properties": {"x": {"type": "string"}},
            "additionalProperties": True,
        }
        result = fix_schema_for_gemini(schema)
        assert "additionalProperties" not in result

    def test_strips_default_values(self):
        schema = {
            "type": "object",
            "properties": {"x": {"type": "string", "default": "foo"}},
        }
        result = fix_schema_for_gemini(schema)
        assert "default" not in result["properties"]["x"]

    def test_expands_property_names_with_additional_properties(self):
        """When additionalProperties has type info + propertyNames enum, expand into explicit properties."""
        schema = {
            "type": "object",
            "propertyNames": {"enum": ["email", "password"]},
            "additionalProperties": {"type": "string"},
            "minProperties": 1,
        }
        result = fix_schema_for_gemini(schema)
        assert "properties" in result
        assert "email" in result["properties"]
        assert "password" in result["properties"]
        assert result["properties"]["email"] == {"type": "string", "nullable": True}
        # propertyNames and minProperties should be removed after expansion
        assert "propertyNames" not in result
        assert "minProperties" not in result
        assert "additionalProperties" not in result

    def test_empty_object_gets_placeholder(self):
        schema = {"type": "object", "properties": {}}
        result = fix_schema_for_gemini(schema)
        assert "_placeholder" in result["properties"]

    def test_form_fill_action_schema_roundtrip(self):
        """The actual FormFillAction schema must survive Gemini transformation with proper type info."""
        from notte_core.actions.actions import FormFillAction

        schema = FormFillAction.model_json_schema()
        result = fix_schema_for_gemini(schema)
        value_schema = result["properties"]["value"]
        assert "properties" in value_schema
        assert "email" in value_schema["properties"]
        assert "username" in value_schema["properties"]
        assert "password" in value_schema["properties"]
        assert len(value_schema["properties"]) > 10

    def test_expanded_properties_are_nullable(self):
        """Expanded properties from propertyNames must be nullable so Gemini doesn't fill all with null."""
        schema = {
            "type": "object",
            "propertyNames": {"enum": ["email", "password"]},
            "additionalProperties": {"type": "string"},
            "minProperties": 1,
        }
        result = fix_schema_for_gemini(schema)
        assert result["properties"]["email"].get("nullable") is True
        assert result["properties"]["password"].get("nullable") is True

    def test_form_fill_expanded_properties_are_nullable(self):
        """FormFillAction expanded properties must be nullable for Gemini."""
        from notte_core.actions.actions import FormFillAction

        schema = FormFillAction.model_json_schema()
        result = fix_schema_for_gemini(schema)
        value_schema = result["properties"]["value"]
        for prop_name, prop_schema in value_schema["properties"].items():
            assert prop_schema.get("nullable") is True, f"Property '{prop_name}' should be nullable"

    def test_inner_llm_completion_schema_roundtrip(self):
        """The full InnerLlmCompletion schema must have form_fill value properties after Gemini transform."""
        from notte_core.agent_types import AgentCompletion

        schema = AgentCompletion.InnerLlmCompletion.model_json_schema()
        result = fix_schema_for_gemini(schema)
        # Find form_fill in oneOf
        form_fill = None
        for item in result["properties"]["action"]["oneOf"]:
            if item.get("properties", {}).get("type", {}).get("const") == "form_fill":
                form_fill = item
                break
        assert form_fill is not None, "form_fill action not found in schema"
        value_schema = form_fill["properties"]["value"]
        assert "properties" in value_schema
        assert len(value_schema["properties"]) > 10


class TestFixSchemaForOpenai:
    """Tests for fix_schema_for_openai to prevent regressions in schema transformation."""

    def test_expands_property_names_with_additional_properties(self):
        schema = {
            "type": "object",
            "title": "test",
            "properties": {
                "value": {
                    "type": "object",
                    "propertyNames": {"enum": ["email", "password"]},
                    "additionalProperties": {"type": "string"},
                    "minProperties": 1,
                },
            },
            "required": ["value"],
        }
        result = fix_schema_for_openai(schema)
        inner = result["json_schema"]["schema"]
        value_schema = inner["properties"]["value"]
        assert "email" in value_schema["properties"]
        assert "password" in value_schema["properties"]
        # Expanded properties are nullable (anyOf with null) and all listed in required
        assert set(value_schema["required"]) == {"email", "password"}
        assert value_schema["properties"]["email"]["anyOf"][1] == {"type": "null"}

    def test_form_fill_action_schema_roundtrip(self):
        """The full InnerLlmCompletion schema must have form_fill value properties after OpenAI transform."""
        from notte_core.agent_types import AgentCompletion

        schema = AgentCompletion.InnerLlmCompletion.model_json_schema()
        result = fix_schema_for_openai(schema)
        inner = result["json_schema"]["schema"]
        # Find form_fill in anyOf (oneOf is converted to anyOf)
        form_fill = None
        for item in inner["properties"]["action"]["anyOf"]:
            if item.get("properties", {}).get("type", {}).get("const") == "form_fill":
                form_fill = item
                break
        assert form_fill is not None, "form_fill action not found in schema"
        value_schema = form_fill["properties"]["value"]
        assert "properties" in value_schema
        assert "email" in value_schema["properties"]
        assert len(value_schema["properties"]) > 10
        # All expanded properties should be in required (nullable via anyOf)
        assert len(value_schema["required"]) == len(value_schema["properties"])

    def test_regular_object_properties_all_required(self):
        """Normal objects (not expanded from propertyNames) should have all properties required."""
        schema = {
            "type": "object",
            "title": "test",
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "integer"},
            },
        }
        result = fix_schema_for_openai(schema)
        inner = result["json_schema"]["schema"]
        assert set(inner["required"]) == {"name", "age"}


class TestStructuredContentExtended:
    def test_extract_with_fail_if_final_tag(self):
        response_text = """
Step 4: Process relevant elements.
- Concatenating following text elements to make the output more readable.
- Removing duplicate text fields that occur multiple times across the same section.

### <data-extraction>
```markdown
# Before you continue to Google
```
"""

        sc = StructuredContent(
            outer_tag="data-extraction",
            inner_tag="markdown",
            fail_if_final_tag=False,
            fail_if_inner_tag=False,
        )
        text = sc.extract(response_text)
        assert text == "# Before you continue to Google"


class TestSchemaRejectionFallback:
    ANTHROPIC_DISCRIMINATOR = "output_format.schema: For 'anyOf', 'discriminator' is not supported"
    ANTHROPIC_UNIONS = (
        "Schemas contains too many parameters with union types (107 parameters with type arrays or anyOf)."
    )
    GROQ_DUPLICATES = "invalid JSON schema for response_format: 'InnerLlmCompletion': duplicate primitive types"

    class Answer(BaseModel):
        text: str

    @pytest.fixture(autouse=True)
    def _fresh_rejection_cache(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("notte_llm.engine._strict_schema_rejected", set())

    @pytest.mark.parametrize("message", [ANTHROPIC_DISCRIMINATOR, ANTHROPIC_UNIONS, GROQ_DUPLICATES])
    def test_detects_provider_schema_rejections(self, message: str) -> None:
        assert is_schema_rejection(message)

    @pytest.mark.parametrize("message", ["Missing API Key", "Invalid JSON response", "max_tokens is too large"])
    def test_ignores_other_bad_requests(self, message: str) -> None:
        assert not is_schema_rejection(message)

    @staticmethod
    def _bad_request(message: str) -> BadRequestError:
        return BadRequestError(message=message, model="m", llm_provider="anthropic")

    @pytest.mark.asyncio
    async def test_completion_maps_schema_rejection(self, llm_engine: LLMEngine) -> None:
        with patch("litellm.acompletion", side_effect=self._bad_request(self.ANTHROPIC_DISCRIMINATOR)):
            with pytest.raises(UnsupportedResponseSchemaError):
                _ = await llm_engine.completion(
                    messages=[Message(role="user", content="Hi")], model="anthropic/x", response_format=self.Answer
                )

    @pytest.mark.asyncio
    async def test_completion_keeps_other_bad_requests_generic(self, llm_engine: LLMEngine) -> None:
        with patch("litellm.acompletion", side_effect=self._bad_request("max_tokens is too large")):
            with pytest.raises(LLMProviderError) as exc_info:
                _ = await llm_engine.completion(
                    messages=[Message(role="user", content="Hi")], model="anthropic/x", response_format=self.Answer
                )
        assert not isinstance(exc_info.value, UnsupportedResponseSchemaError)

    @pytest.mark.asyncio
    async def test_structured_completion_falls_back_to_json_object(self, llm_engine: LLMEngine) -> None:
        formats: list[Any] = []

        def fake_acompletion(*_args: Any, **kwargs: Any) -> Mock:
            formats.append(kwargs.get("response_format"))
            if kwargs.get("response_format") != {"type": "json_object"}:
                raise self._bad_request(self.GROQ_DUPLICATES)
            return Mock(choices=[Mock(message=Mock(content='{"text": "done"}'))])

        messages: list[Any] = [{"role": "user", "content": "Answer"}]
        with patch("litellm.acompletion", side_effect=fake_acompletion):
            first = await llm_engine.structured_completion(messages, self.Answer, model="groq/some-model")
            second = await llm_engine.structured_completion(messages, self.Answer, model="groq/some-model")

        assert first.text == second.text == "done"
        # One rejected strict attempt, then json_object; the second call skips the strict attempt.
        assert formats[1:] == [{"type": "json_object"}, {"type": "json_object"}]
        assert formats[0] != {"type": "json_object"}

    @pytest.mark.asyncio
    async def test_rejection_does_not_leak_to_other_schemas_with_same_name(self, llm_engine: LLMEngine) -> None:
        first = create_model("Choice", text=(str, ...))
        second = create_model("Choice", text=(str, ...), score=(int, ...))
        formats: list[Any] = []

        def fake_acompletion(*_args: Any, **kwargs: Any) -> Mock:
            formats.append(kwargs.get("response_format"))
            is_strict = kwargs.get("response_format") != {"type": "json_object"}
            if is_strict and len(formats) == 1:
                raise self._bad_request(self.GROQ_DUPLICATES)
            return Mock(choices=[Mock(message=Mock(content='{"text": "done", "score": 1}'))])

        messages: list[Any] = [{"role": "user", "content": "Answer"}]
        with patch("litellm.acompletion", side_effect=fake_acompletion):
            _ = await llm_engine.structured_completion(messages, first, model="groq/some-model")
            _ = await llm_engine.structured_completion(messages, second, model="groq/some-model")

        # first: rejected strict + json_object fallback; second: still tries strict first.
        assert formats[1] == {"type": "json_object"}
        assert formats[2] != {"type": "json_object"}


class TestTransientProviderErrors:
    OVERLOADED = "This model is currently experiencing high demand. Please try again later."

    class Answer(BaseModel):
        text: str

    @pytest.fixture(autouse=True)
    def _no_backoff(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def no_sleep(_seconds: float) -> None:
            return None

        monkeypatch.setattr("notte_llm.engine.asyncio.sleep", no_sleep)

    @classmethod
    def _overloaded(cls) -> ServiceUnavailableError:
        return ServiceUnavailableError(message=cls.OVERLOADED, llm_provider="gemini", model="gemini/x")

    @pytest.mark.asyncio
    async def test_retries_an_overloaded_model_then_succeeds(self, llm_engine: LLMEngine) -> None:
        ok = Mock()
        with patch("litellm.acompletion", side_effect=[self._overloaded(), ok]) as acompletion:
            response = await llm_engine.completion(messages=[Message(role="user", content="Hi")], model="gemini/x")
        assert response is ok
        assert acompletion.call_count == 2

    @pytest.mark.asyncio
    async def test_gives_up_after_the_retries(self, llm_engine: LLMEngine) -> None:
        with patch("litellm.acompletion", side_effect=[self._overloaded() for _ in range(3)]) as acompletion:
            with pytest.raises(LLMProviderError):
                _ = await llm_engine.completion(messages=[Message(role="user", content="Hi")], model="gemini/x")
        assert acompletion.call_count == 3

    @pytest.mark.asyncio
    async def test_does_not_retry_a_bad_request(self, llm_engine: LLMEngine) -> None:
        bad = BadRequestError(message="max_tokens is too large", model="gemini/x", llm_provider="gemini")
        with patch("litellm.acompletion", side_effect=bad) as acompletion:
            with pytest.raises(LLMProviderError):
                _ = await llm_engine.completion(messages=[Message(role="user", content="Hi")], model="gemini/x")
        assert acompletion.call_count == 1

    @pytest.mark.asyncio
    async def test_structured_completion_retries_a_response_without_choices(self, llm_engine: LLMEngine) -> None:
        empty = Mock(choices=[])
        ok = Mock(choices=[Mock(message=Mock(content='{"text": "done"}'))])
        messages: list[Any] = [{"role": "user", "content": "Answer"}]
        with patch("litellm.acompletion", side_effect=[empty, ok]):
            result = await llm_engine.structured_completion(messages, self.Answer, model="gemini/x")
        assert result.text == "done"


class TestOpenRouterFallbacks:
    @pytest.fixture(autouse=True)
    def _openrouter_enabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("notte_llm.engine.enable_openrouter", lambda: True)

    def test_requested_model_comes_first_then_fallbacks(self, llm_engine: LLMEngine) -> None:
        body = llm_engine._get_extra_body("vertex_ai/gemini-3.5-flash")  # pyright: ignore[reportPrivateUsage]
        assert body == {"models": ["google/gemini-3.5-flash", *OPENROUTER_FALLBACK_MODELS]}

    def test_fallback_list_does_not_repeat_the_requested_model(self, llm_engine: LLMEngine) -> None:
        body = llm_engine._get_extra_body(f"openrouter/{OPENROUTER_FALLBACK_MODELS[0]}")  # pyright: ignore[reportPrivateUsage]
        assert body["models"] == [OPENROUTER_FALLBACK_MODELS[0], *OPENROUTER_FALLBACK_MODELS[1:]]

    def test_provider_routing_is_kept_alongside_fallbacks(self, llm_engine: LLMEngine) -> None:
        body = llm_engine._get_extra_body("groq/gpt-oss-120b")  # pyright: ignore[reportPrivateUsage]
        assert body["provider"] == {"order": ["Groq"], "allow_fallbacks": True}
        assert body["models"][0] == "openai/gpt-oss-120b"

    def test_no_fallbacks_without_openrouter(self, llm_engine: LLMEngine, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("notte_llm.engine.enable_openrouter", lambda: False)
        assert llm_engine._get_extra_body("gemini/gemini-3.5-flash") == {}  # pyright: ignore[reportPrivateUsage]
