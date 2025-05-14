import datetime as dt
from enum import StrEnum
from pathlib import Path

import chevron
from notte_core.actions.base import (
    BaseAction,
    ClickAction,
    CompletionAction,
    FillAction,
    GotoAction,
    ScrapeAction,
)
from notte_core.actions.registry import ActionRegistry

system_prompt_dir = Path(__file__).parent / "prompts"


class PromptType(StrEnum):
    SINGLE_ACTION = "single_action"
    MULTI_ACTION = "multi_action"

    def prompt_file(self) -> Path:
        match self:
            case PromptType.SINGLE_ACTION:
                return system_prompt_dir / "system_prompt_single_action.md"
            case PromptType.MULTI_ACTION:
                return system_prompt_dir / "system_prompt_multi_action.md"


class FalcoPrompt:
    def __init__(
        self,
        max_actions_per_step: int,
    ) -> None:
        multi_act = max_actions_per_step > 1
        prompt_type = PromptType.MULTI_ACTION if multi_act else PromptType.SINGLE_ACTION
        self.system_prompt: str = prompt_type.prompt_file().read_text()
        self.max_actions_per_step: int = max_actions_per_step
        self.action_registry: ActionRegistry = ActionRegistry()

    @staticmethod
    def _json_dump(steps: list[BaseAction]) -> str:
        lines = ",\n  ".join([action.dump_str() for action in steps])
        return "[\n  " + lines + "\n]"

    def example_form_filling(self) -> str:
        return self._json_dump(
            [FillAction(id="I99", value="username"), FillAction(id="I101", value="password"), ClickAction(id="B1")]
        )

    def example_invalid_sequence(self) -> str:
        return self._json_dump(
            [
                ClickAction(id="L1"),
                ClickAction(id="B4"),
                ClickAction(id="L2"),
            ]
        )

    def example_navigation_and_extraction(self) -> str:
        return self._json_dump([GotoAction(url="https://www.google.com"), ScrapeAction()])

    def completion_example(self) -> str:
        return self._json_dump([CompletionAction(success=True, answer="<answer to the task>")])

    def example_step(self) -> str:
        goal_eval = (
            "Analyze the current elements and the image to check if the previous goals/actions"
            " are successful like intended by the task. Ignore the action result. The website is the ground truth. "
            "Also mention if something unexpected happened like new suggestions in an input field. "
            "Shortly state why/why not"
        )
        return chevron.render(
            """
{
  "state": {
    "page_summary": "On the page are company a,b,c wtih their revenue 1,2,3.",
    "relevant_interactions": [{"id": "B2", "reason": "The button with id B2 represents search and I'm looking to search"}],
    "previous_goal_status": "success|failure|unknown",
    "previous_goal_eval": "{{goal_eval}}",
    "memory": "Description of what has been done and what you need to remember until the end of the task",
    "next_goal": "What needs to be done with the next actions"
  },
  "actions": [
   { "one_action_name": {
      // action-specific parameter
      ...
   }
   }, // ... more actions in sequence ...
  ]
}
""",
            {"goal_eval": goal_eval},
        )

    def system(self) -> str:
        return chevron.render(
            self.system_prompt,
            {
                "timstamp": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "max_actions_per_step": self.max_actions_per_step,
                "action_description": self.action_registry.render(),
                "example_form_filling": self.example_form_filling(),
                "example_step": self.example_step(),
                "completion_example": self.completion_example(),
                "completion_action_name": CompletionAction.name(),
                "goto_action_name": GotoAction.name(),
                "example_navigation_and_extraction": self.example_navigation_and_extraction(),
                "example_invalid_sequence": self.example_invalid_sequence(),
            },
        )

    def task(self, task: str):
        return f"""
Your ultimate task is: "{task}".
If you achieved your ultimate task, stop everything and use the done action in the next step to complete the task.
If not, continue as usual.
"""

    def new_task(self, task: str) -> str:
        return f"""
Your new ultimate task is: {task}.
Take the previous context into account and finish your new ultimate task.
"""

    def action_message(self) -> str:
        return """Given the previous information, start by reflecting on your last action. Then, summarize the current page and list relevant available interactions.
Absolutely do not under any circumstance list or pay attention to any id that is not explicitly found in the page.
From there, select the your next goal, and in turn, your next action.
    """
