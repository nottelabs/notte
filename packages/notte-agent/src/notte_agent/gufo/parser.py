from typing import ClassVar, Literal

from notte_core.actions import ActionParameterValue, CompletionAction, GotoAction, ScrapeAction, StepAction
from typing_extensions import override

from notte_agent.common.parser import BaseParser, NotteStepAgentOutput


class GufoParser(BaseParser):
    observe_tag: ClassVar[str] = "observe"
    step_tag: ClassVar[str] = "execute-action"
    scrape_tag: ClassVar[str] = "scrape-data"
    done_tag: ClassVar[str] = "done"

    @override
    def example_format(self, endpoint: Literal["observe", "step", "scrape", "done", "error"]) -> str | None:
        match endpoint:
            case "observe":
                return f"""
<{self.observe_tag}>
{GotoAction(url="https://www.example.com").model_dump_agent_json()}
</{self.observe_tag}>
"""
            case "step":
                return f"""
<{self.step_tag}>
{
                    StepAction(
                        id="<YOUR_ACTION_ID>",
                        value=ActionParameterValue(name="<YOUR_PARAM_NAME>", value="<YOUR_PARAM_VALUE>"),
                    ).model_dump_agent_json()
                }
</{self.step_tag}>
"""
            case "scrape":
                return f"""
<{self.scrape_tag}>
{ScrapeAction(instructions="<YOUR_SCRAPING_INSTRUCTIONS | null to scrape the whole page>").model_dump_agent_json()}
</{self.scrape_tag}>
"""
            case "done":
                return f"""
<{self.done_tag}>
{CompletionAction(success=True, answer="<YOUR_ANSWER>").model_dump_agent_json()}
</{self.done_tag}>
"""
            case "error":
                return f"""
<{self.done_tag}>
{CompletionAction(success=False, answer="<REASON_FOR_FAILURE>").model_dump_agent_json()}
</{self.done_tag}>
"""

    @override
    def parse(self, text: str) -> NotteStepAgentOutput | None:
        url = self.search_pattern(text, GufoParser.observe_tag)
        action = self.search_pattern(text, GufoParser.step_tag)
        scrape = self.search_pattern(text, GufoParser.scrape_tag)
        output = self.search_pattern(text, GufoParser.done_tag)
        match (bool(url), bool(action), bool(scrape), bool(output)):
            case (True, False, False, False):
                return NotteStepAgentOutput(
                    observe=GotoAction.model_validate(self.parse_json(text, GufoParser.observe_tag))
                )
            case (False, True, False, False):
                return NotteStepAgentOutput(
                    step=StepAction.model_validate(self.parse_json(text, GufoParser.step_tag)),
                )
            case (False, False, True, False):
                return NotteStepAgentOutput(
                    scrape=ScrapeAction.model_validate(self.parse_json(text, GufoParser.scrape_tag))
                )
            case (False, False, False, True):
                return NotteStepAgentOutput(
                    completion=CompletionAction.model_validate(self.parse_json(text, GufoParser.done_tag))
                )
            case _:
                return None
