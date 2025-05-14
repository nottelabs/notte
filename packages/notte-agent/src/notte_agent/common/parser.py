import json
import re
from abc import ABC, abstractmethod
from typing import Literal

from notte_core.actions.base import (
    BaseAction,
    CompletionAction,
    GotoAction,
    ScrapeAction,
)
from notte_core.actions.percieved import ExecPerceivedAction
from pydantic import BaseModel


class NotteStepAgentOutput(BaseModel):
    observe: GotoAction | None = None
    step: ExecPerceivedAction | None = None
    scrape: ScrapeAction | None = None
    completion: CompletionAction | None = None

    @property
    def endpoint(self) -> Literal["observe", "step", "scrape", "done"] | None:
        if self.observe is not None:
            return "observe"
        elif self.step is not None:
            return "step"
        elif self.scrape is not None:
            return "scrape"
        elif self.completion is not None:
            return "done"
        else:
            return None

    @property
    def action(self) -> BaseAction | None:
        if self.observe is not None:
            return self.observe
        elif self.step is not None:
            return self.step
        elif self.scrape is not None:
            return self.scrape
        else:
            return None


class ParameterizedAction(BaseModel):
    action_id: str
    params: dict[str, str] | None = None


class BaseParser(ABC):
    @abstractmethod
    def parse(self, text: str) -> NotteStepAgentOutput | None:
        raise NotImplementedError

    @abstractmethod
    def example_format(self, endpoint: Literal["observe", "step", "scrape"]) -> str | None:
        raise NotImplementedError

    @staticmethod
    def search_pattern(text: str, tag: str) -> str | None:
        pattern = re.compile(rf"<{tag}>(.*?)</{tag}>", re.IGNORECASE | re.DOTALL)
        match = pattern.search(text)
        return match.group(1).strip() if match else None

    @staticmethod
    def parse_json(text: str, tag: str | None = None) -> dict[str, str]:
        if tag is not None:
            _text = BaseParser.search_pattern(text, tag)
            if _text is None:
                raise ValueError(f"No text found within <{tag}> tags")
            text = _text
        try:
            data: dict[str, str] = json.loads(text)
        except json.JSONDecodeError:
            raise ValueError("Invalid JSON in action")
        return data
