from unittest.mock import Mock, patch

import pytest
from litellm import Message
from notte_core.errors.base import ErrorConfig
from notte_llm.engine import LLMEngine, StructuredContent, fix_schema_for_gemini, fix_schema_for_openai


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
        assert result["properties"]["email"] == {"type": "string"}
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
