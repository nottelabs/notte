from dataclasses import dataclass, field
from typing import Any, Literal

from notte.browser.node_type import NotteNode


@dataclass
class ActionParameter:
    name: str
    type: str
    default: str | None = None
    values: list[str] = field(default_factory=list)

    def description(self) -> str:
        base = f"{self.name}: {self.type}"
        if len(self.values) > 0:
            base += f" = [{', '.join(self.values)}]"
        return base

    @staticmethod
    def from_json(json: dict[str, Any]) -> "ActionParameter":
        return ActionParameter(
            name=json["name"],
            type=json["type"],
            values=json["values"],
            default=json["default"],
        )


@dataclass
class ActionParameterValue:
    parameter_name: str
    value: str


@dataclass
class CachedAction:
    status: Literal["valid", "failed", "excluded"]
    description: str
    category: str
    code: str | None
    params: list[ActionParameter] = field(default_factory=list)


@dataclass
class PossibleAction:
    id: str
    description: str
    category: str
    params: list[ActionParameter] = field(default_factory=list)


@dataclass
class Action(PossibleAction):
    status: Literal["valid", "failed", "excluded"] = "valid"

    def markdown(self) -> str:
        return self.description

    def get_role(self) -> str:
        match self.id[0]:
            case "L":
                return "link"
            case "B":
                return "button"
            case "I":
                return "input"
            case _:
                return "other"

    def embedding_description(self) -> str:
        return self.get_role() + " " + self.description

    @staticmethod
    def from_json(json: dict[str, Any]) -> "Action":
        return Action(
            id=json["id"],
            description=json["description"],
            category=json["category"],
            params=[ActionParameter.from_json(param) for param in json["params"]],
            status=json["status"],
        )


@dataclass
class ExecutableAction(Action):
    node: NotteNode | None = None
    params_values: list[ActionParameterValue] = field(default_factory=list)
    code: str | None = None
