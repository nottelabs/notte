import json
import re
from abc import ABC, abstractmethod
from typing import ClassVar, Literal, Required, TypedDict

import chevron
from pydantic import BaseModel
from typing_extensions import override

from notte.browser.observation import Observation


class EnvObserveParams(BaseModel):
    url: str


class EnvStepParams(BaseModel):
    action_id: str
    params: dict[str, str] | None


class ActionJson(TypedDict):
    action_id: Required[str]
    params: dict[str, str] | None


class Parser(ABC):

    @abstractmethod
    def which(self, text: str) -> Literal["observe", "step", "scrape", "rules"]:
        raise NotImplementedError

    @abstractmethod
    def is_done(self, text: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def get_done_answer(self, text: str) -> str | None:
        raise NotImplementedError

    @abstractmethod
    def observe(self, text: str) -> EnvObserveParams:
        raise NotImplementedError

    @abstractmethod
    def step(self, text: str) -> EnvStepParams:
        raise NotImplementedError

    @abstractmethod
    def rules(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def textify(self, obs: Observation) -> str:
        raise NotImplementedError


class BaseNotteParser(Parser):
    observe_tag: ClassVar[str] = "url"
    step_tag: ClassVar[str] = "execute-action"
    scrape_tag: ClassVar[str] = "scrape-data"
    done_tag: ClassVar[str] = "done"

    PRE_INSTRUCTIONS: str = """
Hi there! I am the Notte web environment, and will help you navigate the internet.
How it works: Provide me with a URL. I will respond with the actions you can take on that page.
Important: Make sure to use the **exact format** below when sending me a URL:
<url>https://www.example.com</url>
> So, where would you like to go?
\nImportant rules:
* You are not allowed to talk. Just provide the url you want to go to.
* You are allowed to go to only exactly ONE url.
    """

    POST_INSTRUCTIONS: str = f"""Important rules:
* If you're done, include you final answer in <{done_tag}> tags.
Don't forget to justify why your answer is correct and solves the task.
Don't assume anything, just provide factual information backup by the page you're on.
* If you are not done, provide the action you want to take next in <{step_tag}> tags.
* If you want to stop or you're unable to pursue your goal, just explain your problem inside <{done_tag}>Error: ... </{done_tag}> tags.
* You are allowed to take only exactly ONE action from the list.
* You are ONLY allowed to pick actions from the latest list of actions!
* You are NOT allowed to pick actions from list of actions in previous messages!
* If you feel stuck, remember that you are allowed to use `Special Browser Actions` at any time to:
    * Go to a different url
    * Go back to the previous page
    * Refresh the current page
    * Scrape data from the page
    * Etc
"""

    @staticmethod
    def search_pattern(text: str, tag: str) -> str | None:
        pattern = re.compile(rf"<{tag}>(.*?)</{tag}>", re.IGNORECASE | re.DOTALL)
        match = pattern.search(text)
        return match.group(1).strip() if match else None

    @override
    def which(self, text: str) -> Literal["observe", "step", "scrape", "rules"]:
        url = self.search_pattern(text, BaseNotteParser.observe_tag)
        action = self.search_pattern(text, BaseNotteParser.step_tag)
        scrape = f"<{BaseNotteParser.done_tag}/>" in text
        match (bool(url), bool(action), bool(scrape)):
            case (True, False, False):
                return "observe"
            case (False, True, False):
                return "step"
            case (False, False, True):
                return "scrape"
            case _:
                return "rules"

    @override
    def is_done(self, text: str) -> bool:
        return (
            f"<{BaseNotteParser.done_tag}/>" in text or self.search_pattern(text, BaseNotteParser.done_tag) is not None
        )

    @override
    def get_done_answer(self, text: str) -> str | None:
        if not self.is_done(text):
            raise ValueError("Not done")
        return self.search_pattern(text, BaseNotteParser.done_tag)

    @override
    def observe(self, text: str) -> EnvObserveParams:
        url = self.search_pattern(text, BaseNotteParser.observe_tag)
        if url is None:
            raise ValueError("No URL found")
        return EnvObserveParams(url=url)

    @override
    def step(self, text: str) -> EnvStepParams:
        action = self.search_pattern(text, BaseNotteParser.step_tag)
        if action is None or not isinstance(action, str):
            raise ValueError("No action found")
        try:
            action_dict: ActionJson = json.loads(action)
        except json.JSONDecodeError:
            raise ValueError("Invalid JSON in action")
        action_id = action_dict.get("action_id", None)
        if action_id is None:
            raise ValueError("No action-id found in action")
        params = action_dict.get("params", None)
        return EnvStepParams(action_id=action_id, params=params)

    @override
    def rules(self) -> str:
        return self.PRE_INSTRUCTIONS

    def textify_scrape(
        self,
        obs: Observation,
    ) -> str:
        if not obs.has_data():
            raise ValueError("No scraping data found")
        return f"""
Here is some data that has been extracted from this page:

<{BaseNotteParser.scrape_tag}>
{obs.data}
</{BaseNotteParser.scrape_tag}>
"""

    def textify_step(self, obs: Observation) -> str:
        if not obs.has_space():
            raise ValueError("No actions found")

        template_answer = """
Here are the available actions you can take on this paqe:

<actions>
{{actions}}
</actions>

Now think about your current trajectory, and decide what action to take next.
You might need to perform some intermediate actions so be very careful, dont jump to conclusions too quickly.

Provide me with the ID of the action you want to take next.
You are allowed to take only exactly ONE action from this list (not previous lists)!
If the action is parameterized, provide the value for each parameter.
Use the exact following format:

<execute-action>
{
"action_id": "<YOUR_ACTION_ID>",
"params": { "<YOUR_PARAM_NAME>": "<YOUR_PARAM_VALUE>" }
}
</execute-action>
"""
        return chevron.render(
            template_answer,
            {
                "actions": obs.space.markdown("valid"),
                "extracted_data": obs.data,
            },
        )

    @override
    def textify(self, obs: Observation) -> str:
        match (obs.has_data(), obs.has_space()):
            case (True, True):
                text = f"""
{self.textify_scrape(obs)}
{self.textify_step(obs)}
"""
            case (True, False):
                text = self.textify_scrape(obs)
            case (False, True):
                text = self.textify_step(obs)
            case _:
                raise ValueError("No data or actions found")
        return f"""
Webpage information:
- URL: {obs.url}
- Title: {obs.title}
- Description: {obs.space.description or "No description available"}
- Timestamp: {obs.timestamp.strftime("%Y-%m-%d %H:%M:%S")}
- Page category: {obs.space.category.value if obs.space.category is not None else "No category available"}
{text}
{self.POST_INSTRUCTIONS}
"""
