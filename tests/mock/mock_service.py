from typing import Any, final

import pytest
import tiktoken
from litellm import Message, ModelResponse
from notte_core.llms.engine import LlmModel
from notte_core.llms.service import LLMService
from typing_extensions import override


@final
class MockLLMService(LLMService):
    def __init__(self, mock_response: str):  # noqa: B027
        self.mock_response: str = mock_response
        self.last_messages: list[Message] = []
        self.last_model: str | None = None
        self.tokenizer = tiktoken.encoding_for_model("gpt-4o")
        self.base_model: str = LlmModel.default()

    @override
    async def completion(
        self,
        prompt_id: str,
        variables: dict[str, Any] | None = None,
    ) -> ModelResponse:
        # create a mock ModelResponse
        return ModelResponse(
            id="mock-id",
            choices=[
                {
                    "message": {
                        "content": self.mock_response,
                        "role": "assistant",
                    },
                    "index": 0,
                    "finish_reason": "stop",
                }
            ],
            created=1234567890,
            model="mock-model",
            usage={
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            },
        )


@pytest.fixture
def patch_llm_service(mock_llm_service: MockLLMService, monkeypatch: pytest.MonkeyPatch) -> MockLLMService:
    """Fixture to patch LLMService.from_config to return mock service"""
    monkeypatch.setattr(LLMService, "from_config", lambda: mock_llm_service)
    return mock_llm_service
