from pathlib import Path

from notte_browser.tools.base import BaseTool

from notte_agent.falco.prompt import FalcoPrompt


class GufoPrompt(FalcoPrompt):
    def __init__(self, tools: list[BaseTool] | None = None):
        super().__init__(prompt_file=Path(__file__).parent / "system.md", tools=tools)
