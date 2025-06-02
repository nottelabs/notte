from typing import final

from notte_core.browser.observation import Observation
from typing_extensions import override

from notte_agent.common.perception import BasePerception


@final
class FalcoPerception(BasePerception):
    def __init__(
        self,
        include_step_info: bool = True,
        include_attributes: list[str] | None = None,
    ):
        self.include_attributes = include_attributes
        self.include_step_info = include_step_info

    @override
    def perceive_metadata(self, obs: Observation) -> str:
        if obs.progress is None:
            raise ValueError("Observation has no progress")
        return f"""
You will see the following only once. If you need to remember it and you dont know it yet, write it down in the memory.

* Current url: {obs.metadata.url}
* Current page title: {obs.metadata.title}
* Current date and time: {obs.metadata.timestamp.strftime("%Y-%m-%d %H:%M:%S")}
* Available tabs:
{obs.metadata.tabs}
* Current step: {obs.progress.current_step}/{obs.progress.max_steps}'
"""

    @override
    def perceive(self, obs: Observation) -> str:
        return f"""
[Relevant metadata]
{self.perceive_metadata(obs)}

[Interaction elements and context]
{self.perceive_actions(obs)}

[Data found in the page]
{self.perceive_data(obs)}
"""

    @override
    def perceive_actions(self, obs: Observation) -> str:
        px_above = obs.metadata.viewport.pixels_above
        px_below = obs.metadata.viewport.pixels_below

        more_above = f"... {px_above} pixels above - scroll or scrape content to see more ..."
        more_below = f"... {px_below} pixels below - scroll or scrape content to see more ..."

        space_description = obs.space.description

        return f"""
[Start of page]
{more_above if px_above > 0 else ""}
{space_description or "No content to display"}
{more_below if px_below > 0 else ""}
[End of page]

"""

    @override
    def perceive_data(self, obs: Observation, raw: bool = True) -> str:
        if not obs.has_data() or obs.data is None:
            return ""
        if raw:
            percieved_data = obs.data.markdown
        else:
            structured_data = obs.data.structured
            if structured_data is None or not structured_data.success or structured_data.data is None:
                error_msg = f" with error: {structured_data.error}" if structured_data is not None else ""
                return f"Scraping failed{error_msg}. Please try again with different instructions."
            percieved_data = structured_data.data.model_dump_json()

        return f"""
Data scraped from current page view:

{percieved_data or "No valid data to display"}
"""
