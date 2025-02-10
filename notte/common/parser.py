import json
import re
from abc import ABC, abstractmethod
from typing import ClassVar, Literal, Required

from pydantic import BaseModel
from typing_extensions import TypedDict, override

from notte.sdk.types import ObserveRequest, ScrapeRequest, StepRequest


class TaskOutput(BaseModel):
    success: bool
    answer: str


class NotteStepAgentOutput(BaseModel):
    endpoint: Literal["observe", "step", "scrape", "rules", "done"] = "rules"
    obs_request: ObserveRequest | None = None
    step_request: StepRequest | None = None
    scrape_request: ScrapeRequest | None = None
    output: TaskOutput | None = None


class ActionJson(TypedDict):
    action_id: Required[str]
    params: dict[str, str] | None


class BaseParser(ABC):
    @abstractmethod
    def parse(self, text: str) -> NotteStepAgentOutput:
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


class NotteParser(BaseParser):
    observe_tag: ClassVar[str] = "url"
    step_tag: ClassVar[str] = "execute-action"
    scrape_tag: ClassVar[str] = "scrape-data"
    done_tag: ClassVar[str] = "done"

    @override
    def example_format(self, endpoint: Literal["observe", "step", "scrape", "done", "error"]) -> str | None:
        match endpoint:
            case "observe":
                return "<url>https://www.example.com</url>"
            case "step":
                return f"""
<{self.step_tag}>
{
"action_id": "<YOUR_ACTION_ID>",
"params": { "<YOUR_PARAM_NAME>": "<YOUR_PARAM_VALUE>" }
}
</{self.step_tag}>
"""
            case "scrape":
                return "<scrape/>"
            case "done":
                return f"""
<{self.done_tag}>
{
    "success": "true",
    "answer": "<YOUR_ANSWER>"
}
</{self.done_tag}>
"""
            case "error":
                return f"""
<{self.done_tag}>
{
    "success": "false",
    "answer": "<REASON_FOR_FAILURE>"
}
</{self.done_tag}>
"""

    @override
    def parse(self, text: str) -> NotteStepAgentOutput:
        url = self.search_pattern(text, NotteParser.observe_tag)
        action = self.search_pattern(text, NotteParser.step_tag)
        scrape = f"<{NotteParser.done_tag}/>" in text
        output = self.parse_output(text)
        match (bool(url), bool(action), bool(scrape), bool(output)):
            case (True, False, False, False):
                return NotteStepAgentOutput(
                    endpoint="observe",
                    obs_request=self.parse_observe(text),
                )
            case (False, True, False, False):
                return NotteStepAgentOutput(
                    endpoint="step",
                    step_request=self.parse_step(text),
                )
            case (False, False, True, False):
                return NotteStepAgentOutput(
                    endpoint="scrape",
                    obs_request=self.parse_observe(text),
                )
            case (False, False, False, True):
                return NotteStepAgentOutput(
                    endpoint="done",
                    output=self.parse_output(text),
                )
            case _:
                return NotteStepAgentOutput(
                    endpoint="rules",
                )

    def parse_output(self, text: str) -> TaskOutput | None:
        done_str = self.search_pattern(text, NotteParser.done_tag)
        if done_str is None:
            return None
        return TaskOutput(
            success=done_str.startswith("Error: "),
            answer=done_str.split("Error: ")[1].strip(),
        )

    def parse_observe(self, text: str) -> ObserveRequest | None:
        url = self.search_pattern(text, NotteParser.observe_tag)
        if url is None:
            raise ValueError("No URL found")
        return ObserveRequest(url=url)

    def parse_step(self, text: str) -> StepRequest | None:
        action_dict: StepRequest = StepRequest.model_validate(self.parse_json(text, NotteParser.step_tag))
        return action_dict
