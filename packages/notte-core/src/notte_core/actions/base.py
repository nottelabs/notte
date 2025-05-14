import json
import re
from abc import ABCMeta, abstractmethod
from collections.abc import Sequence
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator
from typing_extensions import override

from notte_core.browser.dom_tree import NodeSelectors
from notte_core.credentials.types import ValueWithPlaceholder
from notte_core.errors.actions import InvalidActionError
from notte_core.errors.processing import InvalidInternalCheckError

# ############################################################
# Action enums
# ############################################################

ActionRole = Literal["link", "button", "input", "special", "image", "option", "misc", "other"]


def get_all_subclasses(cls: type) -> list[type]:
    return list(
        set(
            sub
            for sub in cls.__subclasses__()
            + [subsub for sub in cls.__subclasses__() for subsub in get_all_subclasses(sub)]
        )
    )


class BrowserActionId(StrEnum):
    # Base actions
    GOTO = "S1"
    SCRAPE = "S2"
    # Tab actions
    GO_BACK = "S3"
    GO_FORWARD = "S4"
    RELOAD = "S5"
    GOTO_NEW_TAB = "S6"
    SWITCH_TAB = "S7"
    # Press & Scroll actions
    PRESS_KEY = "S8"
    SCROLL_UP = "S9"
    SCROLL_DOWN = "S10"
    # Session actions
    WAIT = "S11"
    COMPLETION = "S12"
    # SCREENSHOT = "S13"


class InteractionActionId(StrEnum):
    CLICK = "A1"
    FILL = "A2"
    CHECK = "A3"
    SELECT = "A4"
    # LIST_DROPDOWN_OPTIONS = "A5"


# ############################################################
# Browser actions models
# ############################################################


class BaseAction(BaseModel, metaclass=ABCMeta):
    """Base model for all actions."""

    id: str
    category: str
    description: str

    @classmethod
    def non_agent_fields(cls) -> set[str]:
        fields = {
            # Base action fields
            "id",
            "category",
            "description",
            # Interaction action fields
            "selector",
            "press_enter",
            "option_selector",
            "text_label",
            # executable action fields
            "params",
            "code",
            "status",
            "locator",
        }
        if "selector" in cls.model_fields or "locator" in cls.model_fields:
            fields.remove("id")
        return fields

    @classmethod
    def name(cls) -> str:
        """Convert a CamelCase string to snake_case"""
        pattern = re.compile(r"(?<!^)(?=[A-Z])")
        return pattern.sub("_", cls.__name__).lower().replace("_action", "")

    @classmethod
    def tool(cls) -> "ToolAction":
        # Get schema and safely remove common fields
        skip_keys = cls.non_agent_fields().difference(set(["description", "id", "category"]))
        sub_skip_keys = ["title", "$ref"]
        raw_schema = cls.model_json_schema()["properties"].items()
        schema = {
            k: {sub_k: sub_v for sub_k, sub_v in v.items() if sub_k not in sub_skip_keys}
            for k, v in raw_schema
            if k not in skip_keys
        }
        _id: dict[str, str] = schema.pop("id", "No id available")  # type: ignore[type-arg]
        _category: dict[str, str] = schema.pop("category", "No category available")  # type: ignore[type-arg]
        _description: dict[str, str] = schema.pop("description", "No description available")  # type: ignore[type-arg]
        if "default" not in _description:
            raise InvalidInternalCheckError(
                check=f"description should have a default value for {cls.__name__}",
                url="unknown url",
                dev_advice="This should never happen.",
            )
        if "default" not in _id:
            raise InvalidInternalCheckError(
                check=f"id should have a default value for {cls.__name__}",
                url="unknown url",
                dev_advice="This should never happen.",
            )
        if "default" not in _category:
            raise InvalidInternalCheckError(
                check=f"category should have a default value for {cls.__name__}",
                url="unknown url",
                dev_advice="This should never happen.",
            )
        return ToolAction(
            id=_id["default"],
            tool_name=cls.name(),
            description=_description["default"],
            parameters=schema,
            category=_category["default"],
        )

    @abstractmethod
    def execution_message(self) -> str:
        """Return the message to be displayed when the action is executed."""
        return f"🚀 Successfully executed action: {self.description}"

    def dump_dict(self, name: bool = True) -> dict[str, dict[str, Any]]:
        body = self.model_dump(exclude=self.non_agent_fields())
        if name:
            return {self.name(): body}
        return body

    def dump_str(self, name: bool = True) -> str:
        params = json.dumps(self.model_dump(exclude=self.non_agent_fields()))
        if name:
            return "{" + f'"{self.name()}": {params}' + "}"
        return params

    @property
    def role(self, raise_error: bool = False) -> ActionRole:
        match self.id[0]:
            case "L":
                return "link"
            case "B":
                return "button"
            case "I":
                return "input"
            case "O":
                return "option"
            case "M":
                return "misc"
            case "F":
                # figure / image
                return "image"
            case "S":
                return "special"
            case _:
                if raise_error:
                    raise InvalidActionError(
                        self.id, f"First ID character must be one of {ActionRole} but got {self.id[0]}"
                    )
                return "other"


class ToolAction(BaseAction):
    id: str
    tool_name: str
    description: str
    parameters: dict[str, Any]

    @override
    def execution_message(self) -> str:
        return f"🚀 Successfully executed {self.name}: {self.description}"


class BrowserAction(BaseAction, metaclass=ABCMeta):
    """Base model for special actions that are always available and not related to the current page."""

    id: BrowserActionId  # type: ignore
    category: str = "Browser Actions"

    @staticmethod
    def tools() -> Sequence[ToolAction]:
        tools: list[ToolAction] = [cls.tool() for cls in get_all_subclasses(BrowserAction) if cls != CompletionAction]  # pyright: ignore[reportUnknownMemberType]
        # storted by ID
        storted_tools = sorted(tools, key=lambda x: int(x.id[1:]))
        return storted_tools


class GotoAction(BrowserAction):
    id: BrowserActionId = BrowserActionId.GOTO
    description: str = "Goto to a URL (in current tab)"
    url: str

    # Allow 'id' to be a field name
    model_config = {"extra": "forbid", "protected_namespaces": ()}  # type: ignore[reportUnknownMemberType]

    __pydantic_fields_set__ = {"url"}  # type: ignore[reportUnknownMemberType]

    @override
    def execution_message(self) -> str:
        return f"Navigated to '{self.url}' in current tab"


class GotoNewTabAction(BrowserAction):
    id: BrowserActionId = BrowserActionId.GOTO_NEW_TAB
    description: str = "Goto to a URL (in new tab)"
    url: str

    @override
    def execution_message(self) -> str:
        return f"Navigated to '{self.url}' in new tab"


class SwitchTabAction(BrowserAction):
    id: BrowserActionId = BrowserActionId.SWITCH_TAB
    description: str = "Switch to a tab (identified by its index)"
    tab_index: int

    @override
    def execution_message(self) -> str:
        return f"Switched to tab {self.tab_index}"


class ScrapeAction(BrowserAction):
    id: BrowserActionId = BrowserActionId.SCRAPE
    description: str = (
        "Scrape the current page data in text format. "
        "If `instructions` is null then the whole page will be scraped. "
        "Otherwise, only the data that matches the instructions will be scraped. "
        "Instructions should be given as natural language, e.g. 'Extract the title and the price of the product'"
    )
    instructions: str | None = None

    @override
    def execution_message(self) -> str:
        return "Scraped the current page data in text format"


# class ScreenshotAction(BrowserAction):
#     id: BrowserActionId = BrowserActionId.SCREENSHOT
#     description: str = "Take a screenshot of the current page"


class GoBackAction(BrowserAction):
    id: BrowserActionId = BrowserActionId.GO_BACK
    description: str = "Go back to the previous page (in current tab)"

    @override
    def execution_message(self) -> str:
        return "Navigated back to the previous page"


class GoForwardAction(BrowserAction):
    id: BrowserActionId = BrowserActionId.GO_FORWARD
    description: str = "Go forward to the next page (in current tab)"

    @override
    def execution_message(self) -> str:
        return "Navigated forward to the next page"


class ReloadAction(BrowserAction):
    id: BrowserActionId = BrowserActionId.RELOAD
    description: str = "Reload the current page"

    @override
    def execution_message(self) -> str:
        return "Reloaded the current page"


class WaitAction(BrowserAction):
    id: BrowserActionId = BrowserActionId.WAIT
    description: str = "Wait for a given amount of time (in milliseconds)"
    time_ms: int

    @override
    def execution_message(self) -> str:
        return f"Waited for {self.time_ms} milliseconds"


class PressKeyAction(BrowserAction):
    id: BrowserActionId = BrowserActionId.PRESS_KEY
    description: str = "Press a keyboard key: e.g. 'Enter', 'Backspace', 'Insert', 'Delete', etc."
    key: str

    @override
    def execution_message(self) -> str:
        return f"Pressed the keyboard key: {self.key}"


class ScrollUpAction(BrowserAction):
    id: BrowserActionId = BrowserActionId.SCROLL_UP
    description: str = "Scroll up by a given amount of pixels. Use `null` for scrolling up one page"
    # amount of pixels to scroll. None for scrolling up one page
    amount: int | None = None

    @override
    def execution_message(self) -> str:
        return f"Scrolled up by {str(self.amount) + ' pixels' if self.amount is not None else 'one page'}"


class ScrollDownAction(BrowserAction):
    id: BrowserActionId = BrowserActionId.SCROLL_DOWN
    description: str = "Scroll down by a given amount of pixels. Use `null` for scrolling down one page"
    # amount of pixels to scroll. None for scrolling down one page
    amount: int | None = None

    @override
    def execution_message(self) -> str:
        return f"Scrolled down by {str(self.amount) + ' pixels' if self.amount is not None else 'one page'}"


# ############################################################
# Completion action models
# ############################################################


class CompletionAction(BrowserAction):
    id: BrowserActionId = BrowserActionId.COMPLETION
    description: str = "Complete the task by returning the answer and terminate the browser session"
    success: bool
    answer: str

    @override
    def execution_message(self) -> str:
        return f"Completed the task with success: {self.success} and answer: {self.answer}"


# ############################################################
# Interaction actions models
# ############################################################


class InteractionAction(BaseAction, metaclass=ABCMeta):
    id: str
    selector: NodeSelectors | None = Field(default=None, exclude=True)
    category: str = "Interaction Actions"
    press_enter: bool | None = Field(default=None, exclude=True)
    text_label: str | None = Field(default=None, exclude=True)


class ClickAction(InteractionAction):
    id: str
    description: str = "Click on an element of the current page"

    @override
    def execution_message(self) -> str:
        return f"Clicked on the element with text label: {self.text_label}"


class FallbackObserveAction(BaseAction):
    id: str = ""
    category: str = "Browser Actions"
    description: str = "Can't be picked: perform observation"

    @override
    def execution_message(self) -> str:
        return "Performed fallback observation"


class FillAction(InteractionAction):
    id: str
    description: str = "Fill an input field with a value"
    value: str | ValueWithPlaceholder
    clear_before_fill: bool = True

    @field_validator("value", mode="before")
    @classmethod
    def verify_value(cls, value: Any) -> Any:
        """Validator necessary to ignore typing issues with ValueWithPlaceholder"""
        return value

    @override
    def execution_message(self) -> str:
        return f"Filled the input field '{self.text_label}' with the value: '{self.value}'"


class FallbackFillAction(InteractionAction):
    id: str
    description: str = "Fill an input field with a value. Only use if explicitly asked, or you failed to input with the normal fill action"
    value: str | ValueWithPlaceholder
    clear_before_fill: bool = True

    @field_validator("value", mode="before")
    @classmethod
    def verify_value(cls, value: Any) -> Any:
        """Validator necessary to ignore typing issues with ValueWithPlaceholder"""
        return value

    @override
    def execution_message(self) -> str:
        return f"Filled (fallback) the input field '{self.text_label}' with the value: '{self.value}'"


class CheckAction(InteractionAction):
    id: str
    description: str = "Check a checkbox. Use `True` to check, `False` to uncheck"
    value: bool

    @override
    def execution_message(self) -> str:
        return f"Checked the checkbox '{self.text_label}'" if self.text_label is not None else "Checked the checkbox"


class SelectDropdownOptionAction(InteractionAction):
    id: str
    description: str = (
        "Select an option from a dropdown. The `id` field should be set to the select element's id. "
        "Then you can either set the `value` field to the option's text or the `option_id` field to the option's `id`."
    )
    value: str | ValueWithPlaceholder

    @field_validator("value", mode="before")
    @classmethod
    def verify_value(cls, value: Any) -> Any:
        """Validator necessary to ignore typing issues with ValueWithPlaceholder"""
        return value

    @override
    def execution_message(self) -> str:
        return (
            f"Selected the option '{self.value}' from the dropdown '{self.text_label}'"
            if self.text_label is not None and self.text_label != ""
            else f"Selected the option '{self.value}' from the dropdown '{self.id}'"
        )
