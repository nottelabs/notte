from pathlib import Path

import chevron

from .parser import GufoParser

system_prompt_file = Path(__file__).parent / "system.md"


class GufoPrompt:
    def __init__(self, parser: GufoParser):
        self.parser: GufoParser = parser
        self.system_prompt: str = system_prompt_file.read_text()

    def system(self, task: str, url: str | None = None) -> str:
        return chevron.render(self.system_prompt, {"task": task, "url": url or "the web"}, warn=True)

    def env_rules(self) -> str:
        return f"""
Hi there! I am the Notte web environment, and will help you navigate the internet.
# How it works:
* Provide me with a URL. I will respond with the actions you can take on that page.
* You are NOT allowed to provide me with more than one URL.
* Important: Make sure to use the **exact format** below when sending me a URL:
{self.parser.example_format("observe")}
> So, where would you like to go?
"""

    def completion_rules(self) -> str:
        return f"""
# How to format your answer when you're done
## Success answer
* If you're done, include you final answer in <{self.parser.done_tag}> tags.
* Don't forget to justify why your answer is correct and solves the task.
* Don't assume anything, just provide factual information backuped by the page you're on.
Format your answer as follows:
{self.parser.example_format("done")}

## Error answer
* If you feel stuck, remember that you are also allowed to use `Special Browser Actions` at any time to:
    * Go to a different url
    * Go back to the previous page
    * Refresh the current page
    * Scrape data from the page
    * Etc
* If you want to stop or you're unable to pursue your goal, format your answer as follows:
{self.parser.example_format("error")}
"""

    def select_action_rules(self) -> str:
        return f"""
# Next Action Selection
* Provide me with the ID of the action you want to take next.
* You are allowed to take only exactly ONE action from the list.
* You are ONLY allowed to pick actions from the latest list of actions!
* You are NOT allowed to pick actions from list of actions in previous messages!
* If the action is parameterized, provide the value for each parameter.
Use the exact following format:

{self.parser.example_format("step")}
"""
