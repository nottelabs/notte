from typing import final

from notte_browser.session import SessionTrajectoryStep
from notte_core.browser.observation import Observation
from typing_extensions import override

from notte_agent.common.perception import BasePerception, trim_message


@final
class GufoPerception(BasePerception):
    @override
    def perceive_metadata(self, obs: Observation) -> str:
        space_description = obs.space.description
        category: str = obs.space.category.value if obs.space.category is not None else ""
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
        return f"""
Here are the available actions you can take on this page:
<actions>
{obs.space.markdown}
</actions>
"""

    @override
    def perceive(self, obs: Observation) -> str:
        return f"""
{self.perceive_metadata(obs).strip()}
{self.perceive_data(obs).strip() if obs.has_data() else ""}
{self.perceive_actions(obs).strip()}
"""

    @override
    def perceive_action_result(
        self,
        step: SessionTrajectoryStep,
        include_ids: bool = False,
        include_data: bool = False,
    ) -> str:
        action = step.action
        id_str = f" with id={action.id}" if include_ids else ""
        if not step.result.success:
            err_msg = trim_message(step.result.message)
            return f"❌ action '{action.name()}'{id_str} failed with error: {err_msg}"
        success_msg = f"✅ action '{action.name()}'{id_str} succeeded: '{action.execution_message()}'"
        data = step.result.data
        if include_data and data is not None and data.structured is not None and data.structured.data is not None:
            return f"{success_msg}\n\nExtracted JSON data:\n{data.structured.data.model_dump_json()}"
        return success_msg
