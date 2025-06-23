from pathlib import Path

from notte_agent.falco.prompt import FalcoPrompt


class GufoPrompt(FalcoPrompt):
    def __init__(self):
        super().__init__(prompt_file=Path(__file__).parent / "system.md")
