from abc import ABC, abstractmethod

from typing_extensions import override

from notte.common.parser import NotteParser


class BasePrompt(ABC):
    @abstractmethod
    def system_rules(self) -> str:
        pass

    @abstractmethod
    def output_format_rules(self) -> str:
        pass

    @abstractmethod
    def select_action_rules(self) -> str:
        pass


class NottePrompt(BasePrompt):
    def __init__(self, parser: NotteParser):
        self.parser: NotteParser = parser

    @override
    def system_rules(self) -> str:
        return f"""
Hi there! I am the Notte web environment, and will help you navigate the internet.
# How it works
* Provide me with a URL. I will respond with the actions you can take on that page.
* You are NOT allowed to provide me with more than one URL.
* Important: Make sure to use the **exact format** below when sending me a URL:

{self.parser.example_format("observe")}

> So, where would you like to go?
"""

    @override
    def output_format_rules(self) -> str:
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

    @override
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
