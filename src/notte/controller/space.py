import json
import random
from abc import ABCMeta, abstractmethod
from collections.abc import Sequence
from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, Field
from typing_extensions import override

from notte.controller.actions import (
    AllActionRole,
    AllActionStatus,
    BaseAction,
    BrowserAction,
)
from notte.errors.processing import InvalidInternalCheckError


class SpaceCategory(StrEnum):
    HOMEPAGE = "homepage"
    SEARCH_RESULTS = "search-results"
    DATA_FEED = "data-feed"
    ITEM = "item"
    AUTH = "auth"
    FORM = "form"
    MANAGE_COOKIES = "manage-cookies"
    OVERLAY = "overlay"
    PAYMENT = "payment"
    CAPTCHA = "captcha"
    OTHER = "other"

    def is_data(self) -> bool:
        return self.value in [
            SpaceCategory.DATA_FEED.value,
            SpaceCategory.SEARCH_RESULTS.value,
            SpaceCategory.ITEM.value,
        ]


class BaseActionSpace(BaseModel, metaclass=ABCMeta):
    description: Annotated[str, Field(description="Human-readable description of the current web page")]
    category: Annotated[
        SpaceCategory | None,
        Field(description="Category of the action space (e.g., 'homepage', 'search-results', 'item)"),
    ] = None

    @abstractmethod
    def actions(
        self, status: AllActionStatus = "valid", role: AllActionRole = "all", include_browser: bool = True
    ) -> Sequence[BaseAction]:
        raise NotImplementedError("actions should be implemented by the subclass")

    @abstractmethod
    def browser_actions(self) -> Sequence[BrowserAction]:
        raise NotImplementedError("browser_actions should be implemented by the subclass")

    @abstractmethod
    def markdown(self, status: AllActionStatus = "valid", include_browser: bool = True) -> str:
        pass

    def sample(
        self,
        status: AllActionStatus = "valid",
        role: AllActionRole = "all",
    ) -> BaseAction:
        return random.choice(self.actions(status, role))


class ActionSpace(BaseActionSpace):
    """Union of all possible actions"""

    description: str
    raw_actions: list[BaseAction] = Field(default_factory=list)
    action_map: dict[str, type[BaseAction]] = Field(default_factory=dict)
    exclude_actions: set[type[BaseAction]] = Field(default_factory=set)

    @override
    def model_post_init(self, __snapshot: Any) -> None:
        self.action_map = {
            action_cls.name(): action_cls for action_cls in ActionSpace.action_classes(exclude=self.exclude_actions)
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

        def get_all_subclasses(cls: type) -> list[type]:
            return list(
                set(
                    sub
                    for sub in cls.__subclasses__()
                    + [subsub for sub in cls.__subclasses__() for subsub in get_all_subclasses(sub)]
                )
            )

        return [claz for claz in get_all_subclasses(BaseAction) if claz not in exclude]

    @override
    def actions(
        self, status: AllActionStatus = "valid", role: AllActionRole = "all", include_browser: bool = True
    ) -> Sequence[BaseAction]:
        # this dose not work because we need actual paramters to create actions
        # action_cls() for action_cls in self.action_classes()
        actions = self.raw_actions
        if include_browser:
            actions.extend(self.browser_actions())
        return actions

    @override
    def browser_actions(self) -> list[BrowserAction]:
        return []

    @override
    def markdown(self, status: AllActionStatus = "valid", include_browser: bool = True) -> str:
        """Returns a markdown formatted description of all available actions."""
        descriptions: list[str] = []

        for action_name, action_cls in self.action_map.items():
            try:
                # Get schema and safely remove common fields
                skip_keys = action_cls.non_agent_fields().difference(set(["description"]))
                sub_skip_keys = ["title", "$ref"]
                schema = {
                    k: {sub_k: sub_v for sub_k, sub_v in v.items() if sub_k not in sub_skip_keys}
                    for k, v in action_cls.model_json_schema()["properties"].items()
                    if k not in skip_keys
                }
                # schema['id'] = schema['id']['default']
                __description: dict[str, str] = schema.pop("description", "No description available")  # type: ignore[type-arg]
                if "default" not in __description:
                    raise InvalidInternalCheckError(
                        check=f"description should have a default value for {action_cls.__name__}",
                        url="unknown url",
                        dev_advice="This should never happen.",
                    )
                _description: str = __description["default"]
                # Format as: ActionName: {param1: {type: str, description: ...}, ...}
                description = f"""
* "{action_name}" : {_description}. Format:
```json
{json.dumps({action_name: schema})}
```
"""
                descriptions.append(description)
            except Exception as e:
                descriptions.append(f"Error getting schema for {action_cls.__name__}: {str(e)}")

        return "".join(descriptions)
