import json
from typing import Any

from pydantic import BaseModel, Field
from typing_extensions import override

from notte_core.actions.base import (
    BaseAction,
    FallbackObserveAction,
    ToolAction,
    get_all_subclasses,
)
from notte_core.actions.percieved import ExecPerceivedAction, PerceivedAction


class ActionRegistry(BaseModel):
    """Union of all possible actions"""

    action_map: dict[str, type[BaseAction]] = Field(default_factory=dict)
    exclude_actions: set[type[BaseAction]] = Field(
        default_factory=lambda: {FallbackObserveAction, ToolAction, PerceivedAction, ExecPerceivedAction}
    )

    @override
    def model_post_init(self, __snapshot: Any) -> None:
        self.action_map = {
            action_cls.name(): action_cls for action_cls in ActionRegistry.action_classes(exclude=self.exclude_actions)
        }
        disabled_actions = [
            "browser",
            "interaction",
            "executable",
            "action",
        ]
        for action in disabled_actions:
            if action in self.action_map:
                del self.action_map[action]

    @staticmethod
    def action_classes(exclude: set[type[BaseAction]] | None = None) -> list[type[BaseAction]]:
        if exclude is None:
            exclude = set()

        return [claz for claz in get_all_subclasses(BaseAction) if claz not in exclude]

    def render(self) -> str:
        """Returns a markdown formatted description of all available actions."""
        descriptions: list[str] = []

        for action_cls in self.action_map.values():
            tool = action_cls.tool()
            description = f"""
* "{tool.tool_name}" : {tool.description}. Format:
```json
{json.dumps({tool.tool_name: tool.parameters})}
```
"""
            descriptions.append(description)

        return "".join(descriptions)
