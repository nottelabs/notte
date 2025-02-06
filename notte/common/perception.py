from abc import ABC, abstractmethod
from typing import Any

from typing_extensions import override

from notte.browser.observation import Observation


class BasePerception(ABC):

    def __init__(self, include_screenshot: bool = True):
        self.include_screenshot: bool = include_screenshot

    @abstractmethod
    def perceive(self, obs: Observation) -> str:
        pass

    def perceive_content(self, obs: Observation) -> str | list[dict[str, Any]]:
        content = self.perceive(obs)
        if not self.include_screenshot:
            return content
        if obs.screenshot is None:
            raise ValueError("Observation has no screenshot")
        return [
            {"type": "text", "text": content},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{obs.screenshot!s}"}},
        ]


class NottePerception(BasePerception):
    def perceive_metadata(self, obs: Observation) -> str:
        space_description = obs.space.description if obs.space is not None else ""
        category: str = obs.space.category.value if obs.space is not None and obs.space.category is not None else ""
        return f"""
Webpage information:
- URL: {obs.metadata.url}
- Title: {obs.metadata.title}
- Description: {space_description or "No description available"}
- Timestamp: {obs.metadata.timestamp.strftime("%Y-%m-%d %H:%M:%S")}
- Page category: {category or "No category available"}
"""

    @override
    def perceive(self, obs: Observation) -> str:
        if not obs.has_data() and not obs.has_space():
            raise ValueError("No data or actions found")
        return f"""
{self.perceive_metadata(obs)}
{self.perceive_scrape(obs) if obs.has_data() else ""}
{self.perceive_step(obs) if obs.has_space() else ""}
"""

    def perceive_scrape(
        self,
        obs: Observation,
    ) -> str:
        if not obs.has_data():
            raise ValueError("No scraping data found")
        return f"""
Here is some data that has been extracted from this page:

<data>
{obs.data.markdown if obs.data is not None else "No data available"}
</data>
"""

    def perceive_step(self, obs: Observation) -> str:
        if not obs.has_space():
            raise ValueError("No actions found")

        return f"""
Here are the available actions you can take on this page:
<actions>
{obs.space.markdown() if obs.space is not None else "No actions available"}
</actions>
"""
