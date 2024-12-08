from typing import Any

from litellm import Message, ModelResponse


class MockLLMEngine:
    def __init__(self, mock_response: str | None = None):
        self.mock_response = mock_response or "Mock response"
        self.last_messages: list[Message] = []
        self.last_model: str | None = None
        self.last_kwargs: dict[str, Any] = {}

    def completion(
        self,
        messages: list[Message],
        model: str,
        **kwargs,
    ) -> ModelResponse:
        # Store the inputs for assertion in tests
        self.last_messages = messages
        self.last_model = model
        self.last_kwargs = kwargs

        # Create a mock ModelResponse
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
            model=model,
            usage={
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            },
        )
