import re
from dataclasses import dataclass
from typing import ClassVar

import litellm
from litellm import Message, ModelResponse
from loguru import logger

from notte.common.tracer import LlmTracer, LlmUsageFileTracer
from notte.llms.logging import trace_llm_usage


class LLMEngine:
    tracer: ClassVar[LlmTracer] = LlmUsageFileTracer()

    @trace_llm_usage(tracer=tracer)
    def completion(
        self,
        messages: list[Message],
        model: str,
        temperature: float = 0.0,
        n: int = 1,
    ) -> ModelResponse:
        try:
            return litellm.completion(model, messages, temperature=temperature, n=n)

        except Exception as e:
            logger.error(f"Error generating response: {str(e)}")
            logger.exception("Full traceback:")
            raise ValueError(f"Error generating LLM response: {str(e)}")


@dataclass
class StructuredContent:
    """Defines how to extract structured content from LLM responses"""

    outer_tag: str | None = None
    inner_tag: str | None = None
    next_outer_tag: str | None = None

    def extract(
        self,
        text: str,
        fail_if_final_tag: bool = True,
        fail_if_inner_tag: bool = True,
        fail_if_next_outer_tag: bool = True,
    ) -> str:
        """Extract content from text based on defined tags

        Parameters:
            text: The text to extract content from
            fail_if_final_tag: If True, raise an error if the final tag is not found
            fail_if_inner_tag: If True, raise an error if the inner tag is not found
            fail_if_next_outer_tag: If True, raise an error if the next outer tag is not found
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
                if fail_if_final_tag or len(splits) == 1:
                    raise ValueError(f"No content found within <{self.outer_tag}> tags in the response: {text}")
                possible_match = splits[1]
                if (
                    self.next_outer_tag is not None
                    and not fail_if_next_outer_tag
                    and f"<{self.next_outer_tag}>" in possible_match
                ):
                    # retry to split by next outer tag
                    splits = possible_match.split(f"<{self.next_outer_tag}>")
                    if len(splits) == 1:
                        raise ValueError(
                            f"Unexpected error <{self.outer_tag}> should be present in the response: {splits}"
                        )
                    possible_match = splits[0].strip()
                # if there is not html tag in `possible_match` then we can safely return it
                if re.search(r"<[^>]*>", possible_match):
                    raise ValueError(f"No content found within <{self.outer_tag}> tags in the response: {text}")
                content = possible_match

        if self.inner_tag:
            pattern = f"```{self.inner_tag}(.*?)```"
            match = re.search(pattern, content, re.DOTALL)
            if match:
                return match.group(1).strip()
            if fail_if_inner_tag:
                raise ValueError(f"No content found within ```{self.inner_tag}``` blocks in the response: {text}")
            return content

        return content
