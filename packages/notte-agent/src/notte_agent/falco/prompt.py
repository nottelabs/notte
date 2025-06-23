import datetime as dt
import json
from pathlib import Path
from typing import Literal

import chevron
from notte_core.actions import (
    BaseAction,
    ClickAction,
    CompletionAction,
    FormFillAction,
    GotoAction,
    ScrapeAction,
)
from notte_core.errors.processing import InvalidInternalCheckError
from typing_extensions import override

from notte_agent.common.prompt import BasePrompt


class ActionRegistry:
    """Union of all possible actions"""

    @staticmethod
    def render() -> str:
        """Returns a markdown formatted description of all available actions."""
        descriptions: list[str] = []

        for action_name, action_cls in BaseAction.ACTION_REGISTRY.items():
            try:
                # Get schema and safely remove common fields
                skip_keys = action_cls.non_agent_fields().difference(set(["description"]))
                sub_skip_keys = ["title", "$ref"]
                schema = {
                    k: {sub_k: sub_v for sub_k, sub_v in v.items() if sub_k not in sub_skip_keys}
                    for k, v in action_cls.model_json_schema()["properties"].items()
                    if k not in skip_keys
                }
                # schema['id'] = schema['id']['default']
                __description: dict[str, str] = schema.pop("description", "No description available")  # type: ignore[type-arg]
                if "default" not in __description:
                    raise InvalidInternalCheckError(
                        check=f"description should have a default value for {action_cls.__name__}",
                        url="unknown url",
                        dev_advice="This should never happen.",
                    )
                _description: str = __description["default"]
                # Format as: ActionName: {param1: {type: str, description: ...}, ...}
                description = f"""
* "{action_name}" : {_description}. Format:
```json
{json.dumps(schema)}
```
"""
                descriptions.append(description)
            except Exception as e:
                descriptions.append(f"Error getting schema for {action_cls.__name__}: {str(e)}")

        return "".join(descriptions)


class FalcoPrompt(BasePrompt):
    def __init__(self, prompt_file: Path | None = None) -> None:
        if prompt_file is None:
            prompt_file = Path(__file__).parent / "system.md"
        self.system_prompt: str = prompt_file.read_text()
        self.max_actions_per_step: int = 1

    @staticmethod
    def action_registry() -> str:
        return ActionRegistry.render()

    def example_form_filling(self) -> str:
        form_values: dict[Literal["address1", "city", "state"], str] = {
            "address1": "<my address>",
            "city": "<my city>",
            "state": "<my state>",
        }
        return FormFillAction(value=form_values).model_dump_agent_json()  # pyright: ignore [reportArgumentType]

    def example_invalid_sequence(self) -> str:
        return ClickAction(id="X1").model_dump_agent_json()

    def example_navigation_and_extraction(self) -> str:
        return ScrapeAction(
            instructions="Extract the search results from the Google search page"
        ).model_dump_agent_json()

    def completion_example(self) -> str:
        return CompletionAction(success=True, answer="<answer to the task>").model_dump_agent_json()

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
  "action": {
      "type: "one_action_type",
      // action-specific parameter
      ...
   }
}
""",
            {"goal_eval": goal_eval},
        )

    @override
    def system(self) -> str:
        return chevron.render(
            self.system_prompt,
            {
                "timstamp": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "max_actions_per_step": self.max_actions_per_step,
                "action_description": self.action_registry(),
                "example_form_filling": self.example_form_filling(),
                "example_step": self.example_step(),
                "completion_example": self.completion_example(),
                "completion_action_name": CompletionAction.name(),
                "goto_action_name": GotoAction.name(),
                "example_navigation_and_extraction": self.example_navigation_and_extraction(),
                "example_invalid_sequence": self.example_invalid_sequence(),
            },
        )

    @override
    def task(self, task: str) -> str:
        return f"""
Your ultimate task is: "{task}".
If you achieved your ultimate task, stop everything and use the done action in the next step to complete the task.
If not, continue as usual.
"""

    @override
    def select_action(self) -> str:
        return """Given the previous information, start by reflecting on your last action. Then, summarize the current page and list relevant available interactions.
Absolutely do not under any circumstance list or pay attention to any id that is not explicitly found in the page.
From there, select the your next goal, and in turn, your next action.
    """

    @override
    def empty_trajectory(self) -> str:
        return f"""
    No action executed so far...
    Your first action should always be a `{GotoAction.name()}` action with a url related to the task.
    You should reflect what url best fits the task you are trying to solve to start the task, e.g.
    - flight search task => https://www.google.com/travel/flights
    - go to reddit => https://www.reddit.com
    - ...
    ONLY if you have ABSOLUTELY no idea what to do, you can use `https://www.google.com` as the default url.
    THIS SHOULD BE THE LAST RESORT.
    """
