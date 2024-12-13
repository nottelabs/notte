import json
import re
from abc import ABC, abstractmethod
from typing import Literal

import chevron
from pydantic import BaseModel
from typing_extensions import override

from notte.browser.context import Observation


class EnvObserveParams(BaseModel):
    url: str


class EnvStepParams(BaseModel):
    action_id: str
    params: dict[str, str] | None


class Parser(ABC):

    @abstractmethod
    def which(self, text: str) -> Literal["observe", "step", "rules"]:
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

    INSTRUCTIONS: str = """
    Hi there! I am the Notte web environment, and will help you navigate the internet.
    How it works: Provide me with a URL. I will respond with the actions you can take on that page.
    Important: Make sure to use the **exact format** below when sending me a URL:
    <url>https://www.example.com</url>
    > So, where would you like to go?
    \nImportant rules:
    * You are not allowed to talk. Just provide the url you want to go to.
    * You are allowed to go to only exactly ONE url.
    """

    @staticmethod
    def search_pattern(text: str, tag: str) -> str | None:
        pattern = re.compile(rf"<{tag}>(.*?)</{tag}>", re.IGNORECASE | re.DOTALL)
        match = pattern.search(text)
        return match.group(1).strip() if match else None

    @override
    def which(self, text: str) -> Literal["observe", "step", "rules"]:
        url = self.search_pattern(text, "url")
        action = self.search_pattern(text, "action")
        match (bool(url), bool(action)):
            case (True, False):
                return "observe"
            case (False, True):
                return "step"
            case _:
                return "rules"

    @override
    def observe(self, text: str) -> EnvObserveParams:
        url = self.search_pattern(text, "url")
        if url is None:
            raise ValueError("No URL found")
        return EnvObserveParams(url=url)

    @override
    def step(self, text: str) -> EnvStepParams:
        action = self.search_pattern(text, "action")
        if action is None or not isinstance(action, str):
            raise ValueError("No action found")
        d = json.loads(action)
        if "action-id" not in d:
            raise ValueError("No action-id found in action")
        action_id = d["action-id"]
        params = d.get("params", None)
        return EnvStepParams(action_id=action_id, params=params)

    @override
    def rules(self) -> str:
        return self.INSTRUCTIONS

    @override
    def textify(self, obs: Observation) -> str:
        if obs.space is None:
            raise ValueError("No actions found")

        s = """
The current URL is: {{url}}
Here are the available actions:
{{actions}}
\n Now think about your current trajectory, and decide what action to take next.
You might need to perform some intermediate actions so be very careful, dont jump to conclusions too quickly.
\nProvide me with the ID of the action you want to take next.
You are allowed to take only exactly ONE action from this list (not previous lists)!
If the action is parameterized, provide the value for each parameter.
Use the exact following format:
<action>
{
"action-id": "<YOUR_ACTION_ID>",
"params": { "<YOUR_PARAM_NAME>": "<YOUR_PARAM_VALUE>" }
}
</action>
\nIf you're done, just say <done/>. Nothing else!
\nImportant rules:
* You are not allowed to talk. Just provide the action you want to take or <done/>.
* You are allowed to take only exactly ONE action from the list.
* Your action should be inside the <action> tag.
* If you're unable to pursue your goal, just say <done/>. Nothing else!
* You are ONLY allowed to pick actions from the latest list of actions!
* You are NOT allowed to pick actions from list of actions in previous messages!c
\n You are allowed to use <url> to navigate to a different url.
"""
        return chevron.render(s, {"url": obs.url, "actions": obs.space.markdown("valid")})
