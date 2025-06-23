from notte_core.actions import BaseAction
from notte_core.browser.observation import Observation, StepResult, TrajectoryProgress
from notte_core.browser.snapshot import SnapshotMetadata
from notte_core.data.space import DataSpace
from notte_core.space import ActionSpace
from typing_extensions import override

from notte_agent.common.perception import BasePerception, trim_message


class FalcoPerception(BasePerception):
    @override
    def perceive_metadata(self, metadata: SnapshotMetadata, progress: TrajectoryProgress) -> str:
        return f"""
You will see the following only once. If you need to remember it and you dont know it yet, write it down in the memory.

* Current url: {metadata.url}
* Current page title: {metadata.title}
* Current date and time: {metadata.timestamp.strftime("%Y-%m-%d %H:%M:%S")}
* Available tabs:
{metadata.tabs}
* Current step: {progress.current_step}/{progress.max_steps}'
"""

    @override
    def perceive(self, obs: Observation) -> str:
        if obs.progress is None:
            raise ValueError("Observation has no progress")
        px_above = obs.metadata.viewport.pixels_above
        px_below = obs.metadata.viewport.pixels_below

        more_above = f"... {px_above} pixels above - scroll or scrape content to see more ..."
        more_below = f"... {px_below} pixels below - scroll or scrape content to see more ..."
        return f"""
[Relevant metadata]
{self.perceive_metadata(obs.metadata, obs.progress)}

[Interaction elements and context]
[Start of page]
{more_above if px_above > 0 else ""}
{self.perceive_actions(obs.space)}
{more_below if px_below > 0 else ""}
[End of page]
"""

    @override
    def perceive_actions(self, space: ActionSpace) -> str:
        return space.description

    @override
    def perceive_data(self, data: DataSpace | None, only_structured: bool = True) -> str:
        if data is None:
            return ""
        if only_structured:
            structured_data = data.structured
            if structured_data is None or not structured_data.success or structured_data.data is None:
                error_msg = f" with error: {structured_data.error}" if structured_data is not None else ""
                return f"Scraping failed{error_msg}. Please try again with different instructions."
            return f"""
Extracted JSON data:
```json
{structured_data.data.model_dump_json()}
```
"""
        return f"""
Data scraped from current page view:
```markdown
{data.markdown or "No valid data to display"}
```
"""

    @override
    def perceive_action_result(
        self,
        action: BaseAction,
        result: StepResult,
        include_ids: bool = False,
        include_data: bool = True,
    ) -> str:
        id_str = f" with id={action.id}" if include_ids else ""
        if not result.success:
            err_msg = trim_message(result.message)
            return f"❌ action '{action.name()}'{id_str} failed with error: {err_msg}"
        success_msg = f"✅ action '{action.name()}'{id_str} succeeded: '{action.execution_message()}'"
        if include_data:
            return f"{success_msg}{self.perceive_data(result.data, only_structured=True)}"
        return success_msg
