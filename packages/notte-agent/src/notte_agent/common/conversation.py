from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any, TypeVar

from litellm import (
    AllMessageValues,
    ChatCompletionAssistantMessage,
    ChatCompletionAssistantToolCall,
    ChatCompletionImageObject,
    ChatCompletionSystemMessage,
    ChatCompletionTextObject,
    ChatCompletionToolMessage,
    ChatCompletionUserMessage,
    ModelResponse,  # type: ignore[reportPrivateImportUsage]
    OpenAIMessageContent,
)
from litellm.utils import token_counter  # type: ignore[reportUnknownVariableType]
from loguru import logger
from notte_core.common.config import LlmModel, config
from notte_core.errors.llm import LLMParsingError
from notte_core.llms.engine import StructuredContent
from pydantic import BaseModel, Field, PrivateAttr
from typing_extensions import override


# Define valid message roles
# /!\ CachedMessage should stay a dataclass. Don't try to make it a BaseModel it will create some weird issues
# Cf error in https://github.com/nottelabs/notte/pull/285.
@dataclass
class CachedMessage:
    """Message with cached token count"""

    message: AllMessageValues
    token_count: int


T = TypeVar("T", bound=BaseModel)


class Conversation(BaseModel):
    """Manages conversation history and message extraction"""

    history: list[CachedMessage] = Field(default_factory=list)
    json_extractor: StructuredContent = Field(default_factory=lambda: StructuredContent(inner_tag="json"))
    autosize: bool = False
    model: str = Field(default_factory=LlmModel.default)
    max_tokens: int | None = config.max_history_tokens
    conservative_factor: float = 0.8

    _total_tokens: int = PrivateAttr(default=0)
    convert_tools_to_assistant: bool = False

    @override
    def model_post_init(self, __context: Any) -> None:
        if self.max_tokens is None:
            self.max_tokens = LlmModel.get_provider(self.model).context_length

    @property
    def default_max_tokens(self) -> int:
        if self.max_tokens is None:
            raise ValueError("max_tokens is not set")
        return self.max_tokens

    @property
    def conservative_max_tokens(self) -> int:
        """Since token count isn't 100% accurate, allow to be
        slightly conservative, to make sure we trim under the total context length"""
        return int(self.default_max_tokens * self.conservative_factor)

    def count_tokens(self, content: AllMessageValues) -> int:
        """Count the number of tokens in a list of messages"""
        return token_counter(model=self.model, messages=[content])

    def total_tokens(self) -> int:
        """Get total tokens in conversation history"""
        return self._total_tokens

    def trim_history_to_fit(self, new_content: AllMessageValues) -> None:
        """Trim history to make room for new content while preserving system messages"""
        if not self.autosize:
            return

        # Always keep system messages
        init_messages: list[CachedMessage] = []
        other_messages: list[CachedMessage] = []
        is_init_msg = True
        for msg in self.history:
            match is_init_msg, msg.message["role"]:
                case True, "system":
                    init_messages.append(msg)
                case True, "user":
                    # keep first user message as init message (need task description)
                    is_init_msg = False
                    init_messages.append(msg)
                case _, _:
                    other_messages.append(msg)

        new_content_tokens = self.count_tokens(new_content)
        init_tokens = sum(msg.token_count for msg in init_messages)
        available_tokens = self.conservative_max_tokens - init_tokens - new_content_tokens

        # Remove oldest non-system messages until we have room
        current_tokens = sum(msg.token_count for msg in other_messages)
        has_trimmed = 0
        while other_messages and current_tokens > available_tokens:
            removed = other_messages.pop(0)
            current_tokens -= removed.token_count
            has_trimmed += 1

        if has_trimmed > 0:
            logger.info(
                f"Trimmed {has_trimmed} message(s) to stay under max token limit (i.e {self.default_max_tokens // 1000}k)"
            )

        self.history = init_messages + other_messages
        self._total_tokens = sum(msg.token_count for msg in self.history)

    def _add_message(self, msg: AllMessageValues) -> None:
        """Internal helper to add a message with token counting"""
        token_count = self.count_tokens(msg)
        if self.autosize:
            self.trim_history_to_fit(msg)
        cached_msg = CachedMessage(message=msg, token_count=token_count)
        self.history.append(cached_msg)
        self._total_tokens += token_count

    def add_system_message(self, content: str) -> None:
        """Add a system message to the conversation"""
        self._add_message(ChatCompletionSystemMessage(role="system", content=content))

    def format_image_content(self, image: bytes) -> ChatCompletionImageObject:
        image_str = base64.b64encode(image).decode("utf-8")
        return ChatCompletionImageObject(
            type="image_url",
            image_url={"url": f"data:image/png;base64,{image_str}"},
        )

    def format_user_contents(self, contents: list[str | bytes]) -> OpenAIMessageContent:
        return [
            (
                ChatCompletionTextObject(type="text", text=content)
                if isinstance(content, str)
                else self.format_image_content(content)
            )
            for content in contents
        ]

    def add_user_message(self, content: OpenAIMessageContent, image: bytes | None = None) -> None:
        """Add a user message to the conversation"""
        _content: OpenAIMessageContent = content
        if image is not None and isinstance(content, str):
            _content = self.format_user_contents([content, image])
        self._add_message(ChatCompletionUserMessage(role="user", content=_content))

    def add_user_messages(self, contents: list[str | bytes]) -> None:
        """Add a user message to the conversation"""
        _content: OpenAIMessageContent = self.format_user_contents(contents)
        self._add_message(ChatCompletionUserMessage(role="user", content=_content))

    def add_assistant_message(self, content: str) -> None:
        """Add an assistant message to the conversation"""
        self._add_message(ChatCompletionAssistantMessage(role="assistant", content=content))

    def add_tool_message(self, parsed_content: BaseModel, tool_id: str) -> None:
        """Add a tool message to the conversation"""
        content: str = str(parsed_content.model_dump(mode="json", exclude_unset=True))
        if not self.convert_tools_to_assistant:
            self._add_message(
                ChatCompletionToolMessage(
                    role="tool",
                    content=content,
                    tool_call_id=tool_id,
                )
            )
        else:
            # Optional, convert tools to assistant role
            self._add_message(
                ChatCompletionAssistantMessage(
                    role="assistant",
                    content="",
                    tool_calls=[
                        ChatCompletionAssistantToolCall(
                            id=tool_id,
                            type="function",
                            function={
                                "arguments": content,
                                "name": parsed_content.__class__.__name__,
                            },
                        )
                    ],
                )
            )

    def parse_structured_response(self, response: ModelResponse | str, model: type[T]) -> T:
        """Parse a structured response from the LLM into a Pydantic model

        Args:
            response: The LLM model response
            model: The Pydantic model class to parse into

        Returns:
            Instance of the specified Pydantic model

        Raises:
            LLMParsingError: If response cannot be parsed into the model
        """
        if isinstance(response, str):
            return model.model_validate(response)
        if not response.choices:
            raise LLMParsingError("No choices in LLM response")

        choice = response.choices[0]
        # Extract content from either streaming or non-streaming response
        content: str | None = None
        if isinstance(choice, dict):
            message = choice.get("message", {})  # type: ignore[reportUnknownMemberType]
            if isinstance(message, dict):
                content = message.get("content")  # type: ignore[reportUnknownMemberType]
        else:
            content = getattr(choice, "text")

        if not content:
            raise LLMParsingError("No content in LLM response message")

        try:
            if content is None or not isinstance(content, str):
                raise LLMParsingError("No content in LLM response message")
            extracted = self.json_extractor.extract(content)
            return model.model_validate_json(extracted)
        except (json.JSONDecodeError, ValueError) as e:
            raise LLMParsingError(f"Failed to parse response into {model.__name__}: {str(e)}")

    def messages(self) -> list[AllMessageValues]:
        """Get messages in LiteLLM format

        Returns:
            List of messages formatted for LiteLLM

        Note:
            This converts our internal message format to litellm's format.
            litellm only supports 'assistant' role, so we map all roles to that.
        """
        return [msg.message for msg in self.history]

    def reset(self) -> None:
        """Clear all messages from the conversation"""
        self.history.clear()
        self._total_tokens = 0
