from pathlib import Path

from notte_core.actions import GotoAction
from typing_extensions import override

from notte_agent.common.prompt import BasePrompt

system_prompt_file = Path(__file__).parent / "system.md"


class GufoPrompt(BasePrompt):
    def __init__(self):
        self.system_prompt: str = system_prompt_file.read_text()

    @override
    def system(self) -> str:
        return self.system_prompt

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
