from typing import final

from notte_core.browser.observation import Observation


@final
class ObservationPerception:
    def perceive(self, obs: Observation) -> str:
        px_above = obs.metadata.viewport.pixels_above
        px_below = obs.metadata.viewport.pixels_below

        more_above = f"... {px_above} pixels above - scroll or scrape content to see more ..."
        more_below = f"... {px_below} pixels below - scroll or scrape content to see more ..."
        return f"""
[Relevant metadata]
* Current url: {obs.metadata.url}
* Current page title: {obs.metadata.title}
* Current date and time: {obs.metadata.timestamp.strftime("%Y-%m-%d %H:%M:%S")}
* Available tabs:
{obs.metadata.tabs}

[Interaction elements and context]
[Start of page]
{more_above if px_above > 0 else ""}
{obs.space.description}
{more_below if px_below > 0 else ""}
[End of page]
"""
