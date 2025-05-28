from unittest.mock import Mock, patch

import pytest
from litellm import Message
from notte_core.errors.base import ErrorConfig
from notte_core.llms.engine import LLMEngine, StructuredContent


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
