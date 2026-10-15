import json

import httpx
import pytest
from notte_core.actions import ActionUnion
from notte_core.errors import ErrorConfig, LLMParsingError, UnsupportedResponseSchemaError
from notte_llm.engine import LLMEngine, StructuredContent, fix_schema_for_openai, is_schema_rejection
from pydantic import BaseModel, create_model


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


class _ActionHolder(BaseModel):
    """Structured output holding any action, as LLM callers ask for."""

    action: ActionUnion


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
        """Finite form field names retain their typed nullable values in strict mode."""
        from notte_core.actions.actions import FormFillAction

        result = fix_schema_for_openai(FormFillAction.model_json_schema())
        inner = result["json_schema"]["schema"]
        value_schema = inner["properties"]["value"]
        assert "email" in value_schema["properties"]
        assert len(value_schema["properties"]) > 10
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


class Answer(BaseModel):
    text: str


@pytest.fixture
def engine_factory(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("NOTTE_LLM_API_KEY", "test-key")
    monkeypatch.delenv("NOTTE_LLM_BASE_URL", raising=False)

    def make(handler, **kwargs):
        return LLMEngine(transport=httpx.MockTransport(handler), **kwargs)

    return make


def reply(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


@pytest.mark.parametrize(
    "message",
    [
        "output_format.schema: For 'anyOf', 'discriminator' is not supported",
        "Schemas contains too many parameters with union types",
        "invalid JSON schema for response_format: duplicate primitive types",
        "response_format.type: Input should be 'json_schema'",
    ],
)
def test_detects_provider_schema_rejections(message):
    assert is_schema_rejection(message)


@pytest.mark.parametrize("message", ["Missing API Key", "Invalid JSON response", "max_tokens is too large"])
def test_ignores_other_bad_requests(message):
    assert not is_schema_rejection(message)


@pytest.mark.asyncio
@pytest.mark.parametrize("status,message", [(400, "invalid JSON schema"), (404, "No endpoints"), (400, "Invalid JSON")])
async def test_strict_fallback_preserves_schema_and_callers_messages(engine_factory, status, message):
    bodies = []

    def handler(request):
        body = json.loads(request.content)
        bodies.append(body)
        if body.get("response_format", {}).get("type") == "json_schema":
            return httpx.Response(status, json={"error": {"message": message}})
        return reply('{"text":"done"}')

    engine = engine_factory(handler, nb_retries_structured_output=0)
    messages = [{"role": "user", "content": "Answer"}]
    assert (await engine.structured_completion(messages, Answer)).text == "done"
    assert [b["response_format"]["type"] for b in bodies] == ["json_schema", "json_object"]
    assert messages == [{"role": "user", "content": "Answer"}]
    assert json.loads(bodies[1]["messages"][-1]["content"].split("JSON schema: ", 1)[1]) == Answer.model_json_schema()


@pytest.mark.asyncio
async def test_json_object_rejection_uses_schema_in_prompt_without_format(engine_factory):
    bodies = []

    def handler(request):
        body = json.loads(request.content)
        bodies.append(body)
        if "response_format" in body:
            return httpx.Response(400, json={"error": {"message": "response_format unsupported"}})
        return reply('{"text":"done"}')

    engine = engine_factory(handler, nb_retries_structured_output=0)
    assert (await engine.structured_completion([{"role": "user", "content": "Answer"}], Answer)).text == "done"
    assert len(bodies) == 3
    assert "response_format" not in bodies[-1]
    assert bodies[-1]["messages"] == bodies[-2]["messages"]


@pytest.mark.asyncio
async def test_rejections_are_not_cached_across_calls_or_schemas(engine_factory):
    bodies = []

    def handler(request):
        body = json.loads(request.content)
        bodies.append(body)
        if body["response_format"]["type"] == "json_schema":
            return httpx.Response(400, json={"error": {"message": "invalid JSON schema"}})
        return reply('{"text":"done","score":1}')

    engine = engine_factory(handler)
    for schema in (Answer, Answer, create_model("Answer", text=(str, ...), score=(int, ...))):
        await engine.structured_completion([{"role": "user", "content": "Answer"}], schema)
    assert [b["response_format"]["type"] for b in bodies] == ["json_schema", "json_object"] * 3


@pytest.mark.asyncio
async def test_fallback_stops_when_prompt_only_request_is_rejected(engine_factory):
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(400, json={"error": {"message": "response_format unsupported"}})

    with pytest.raises(UnsupportedResponseSchemaError):
        await engine_factory(handler).structured_completion([{"role": "user", "content": "Answer"}], Answer)
    assert len(bodies) == 3


@pytest.mark.asyncio
async def test_structured_completion_keeps_the_callers_messages(engine_factory):
    class Number(BaseModel):
        value: int

    contents = iter(["not json", '{"value":"nan"}', '{"value":3}'])
    seen = []

    def handler(request):
        seen.append(len(json.loads(request.content)["messages"]))
        return reply(next(contents))

    messages = [{"role": "user", "content": "How much?"}]
    assert (await engine_factory(handler).structured_completion(messages, Number)).value == 3
    assert seen == [1, 2, 3]
    assert messages == [{"role": "user", "content": "How much?"}]


@pytest.mark.asyncio
@pytest.mark.parametrize("content", ['{"text":"done",}', '{text:"done"}', '{"text":"done" "unused":true}'])
async def test_repairs_malformed_json(engine_factory, content):
    assert (await engine_factory(lambda _: reply(content)).structured_completion([], Answer)).text == "done"


@pytest.mark.asyncio
async def test_parsing_failure_has_a_bounded_retry_count(engine_factory):
    calls = []

    def handler(request):
        calls.append(request)
        return reply('{"wrong":1}')

    with pytest.raises(LLMParsingError):
        await engine_factory(handler).structured_completion([], Answer)
    assert len(calls) == 3


def test_repair_does_not_accept_data_with_wrong_schema():
    assert LLMEngine._try_repair_json('{"wrong":1,}', Answer) is None


class TestGenericSchemaCleaning:
    def test_strips_defaults_and_closes_objects(self):
        schema = {
            "type": "object",
            "properties": {"x": {"type": "string", "default": "foo"}},
            "additionalProperties": False,
        }
        result = fix_schema_for_openai(schema)["json_schema"]["schema"]
        assert "default" not in result["properties"]["x"]
        assert result["additionalProperties"] is False

    def test_empty_object_has_explicit_properties(self):
        result = fix_schema_for_openai({"type": "object"})["json_schema"]["schema"]
        assert result == {"type": "object", "properties": {}, "additionalProperties": False, "required": []}

    def test_schema_name_is_sanitized_and_refs_are_inlined(self):
        class Nested(BaseModel):
            value: Answer

        result = fix_schema_for_openai(Nested.model_json_schema())
        assert "$ref" not in json.dumps(result)
        assert result["json_schema"]["schema"]["properties"]["value"]["properties"]["text"]["type"] == "string"
        result = fix_schema_for_openai({"title": "illegal name[]" * 10, "type": "object"})
        assert len(result["json_schema"]["name"]) == 64
        assert " " not in result["json_schema"]["name"]


def test_schema_properties_can_be_named_after_keywords():
    class Keywords(BaseModel):
        properties: str
        required: str
        additionalProperties: str

    schema = fix_schema_for_openai(Keywords.model_json_schema())["json_schema"]["schema"]
    assert set(schema["properties"]) == {"properties", "required", "additionalProperties"}
    assert schema["properties"]["properties"] == {"type": "string"}
