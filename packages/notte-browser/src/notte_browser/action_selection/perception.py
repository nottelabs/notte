from typing import final

from notte_core.browser.observation import Observation


@final
class ObservationPerception:
    def perceive_metadata(self, obs: Observation) -> str:
        space_description = obs.space.description
        category: str = obs.space.category.value if obs.space.category is not None else ""
        return f"""
Webpage information:
- URL: {obs.metadata.url}
- Title: {obs.metadata.title}
- Description: {space_description or "No description available"}
- Current date and time: {obs.metadata.timestamp.strftime("%Y-%m-%d %H:%M:%S")}
- Page category: {category or "No category available"}
"""

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

    def perceive_actions(self, obs: Observation) -> str:
        return f"""
Here are the available actions you can take on this page:
<actions>
{obs.space.markdown}
</actions>
"""

    def perceive(self, obs: Observation) -> str:
        return f"""
{self.perceive_metadata(obs).strip()}
{self.perceive_data(obs).strip() if obs.has_data() else ""}
{self.perceive_actions(obs).strip()}
"""
