from typing import final

from typing_extensions import override

from notte.browser.observation import Observation
from notte.common.agent.perception import BasePerception


@final
class GufoPerception(BasePerception):
    @override
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
    def perceive_data(
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

    @override
    def perceive_actions(self, obs: Observation) -> str:
        if not obs.has_space():
            raise ValueError("No actions found")

        return f"""
Here are the available actions you can take on this page:
<actions>
{obs.space.markdown() if obs.space is not None else "No actions available"}
</actions>
"""

    @override
    def perceive(self, obs: Observation) -> str:
        if not obs.has_data() and not obs.has_space():
            raise ValueError("No data or actions found")
        return f"""
{self.perceive_metadata(obs).strip()}
{self.perceive_data(obs).strip() if obs.has_data() else ""}
{self.perceive_actions(obs).strip() if obs.has_space() else ""}
"""
