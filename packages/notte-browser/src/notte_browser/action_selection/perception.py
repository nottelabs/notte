from typing import final

from notte_core.browser.observation import Observation


@final
class ObservationPerception:
    def perceive(self, obs: Observation) -> str:
        space_description = obs.space.description
        category: str = obs.space.category.value if obs.space.category is not None else ""
        return f"""
Webpage information:
- URL: {obs.metadata.url}
- Title: {obs.metadata.title}
- Description: {space_description or "No description available"}
- Current date and time: {obs.metadata.timestamp.strftime("%Y-%m-%d %H:%M:%S")}
- Page category: {category or "No category available"}

Here are the available actions you can take on this page:
<actions>
{obs.space.markdown}
</actions>
"""
