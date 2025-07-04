import datetime as dt
import inspect
import json
import operator
import re
import warnings
from abc import ABCMeta, abstractmethod
from functools import reduce
from typing import Annotated, Any, ClassVar, Literal

from pydantic import BaseModel, Field, field_validator
from typing_extensions import override

from notte_core.browser.dom_tree import NodeSelectors
from notte_core.credentials.types import ValueWithPlaceholder

warnings.filterwarnings(
    "ignore", message='Field name "id" in "InteractionAction" shadows an attribute', category=UserWarning
)

warnings.filterwarnings(
    "ignore",
    message=r"Default value <property object at 0x[0-9a-f]+> is not JSON serializable; excluding default from JSON schema \[non-serializable-default\]",
    category=UserWarning,
)

# ############################################################
# Action enums
# ############################################################

EXCLUDED_ACTIONS = {"fallback_observe"}

typeAlias = type


class ActionParameter(BaseModel):
    name: str
    type: str
    default: str | None = None
    values: list[str] = Field(default_factory=list)

    def description(self) -> str:
        base = f"{self.name}: {self.type}"
        if len(self.values) > 0:
            base += f" = [{', '.join(self.values)}]"
        return base


class ActionParameterValue(BaseModel):
    name: str
    value: str | ValueWithPlaceholder


# ############################################################
# Browser actions models
# ############################################################


class BaseAction(BaseModel, metaclass=ABCMeta):
    """Base model for all actions."""

    type: str
    category: Annotated[str, Field(exclude=True, description="Category of the action", min_length=1)]
    description: Annotated[str, Field(exclude=True, description="Description of the action", min_length=1)]

    @property
    def id(self) -> str:
        data = self.model_dump()
        if "id" in data:
            return data["id"]
        return self.type

    @field_validator("type", mode="after")
    @classmethod
    def verify_type_equals_name(cls, value: Any) -> Any:
        """Validator necessary to ignore typing issues with ValueWithPlaceholder"""
        # assert type == cls.name()

        if value != cls.name():
            raise ValueError(f"Action type {value} does not match class name: {cls.name()}")
        return value

    ACTION_REGISTRY: ClassVar[dict[str, typeAlias["BaseAction"]]] = {}

    def __init_subclass__(cls, **kwargs: dict[Any, Any]):
        super().__init_subclass__(**kwargs)  # type: ignore

        if not inspect.isabstract(cls):
            name = cls.name()
            if name in EXCLUDED_ACTIONS:
                return
            if name in {"browser", "interaction", "step", "action", "fallback_observe"}:
                return
            if name in cls.ACTION_REGISTRY:
                raise ValueError(f"Base Action {name} is duplicated")
            cls.ACTION_REGISTRY[name] = cls

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
        }
        if "selector" in cls.model_fields:
            fields.remove("id")
        return fields

    @classmethod
    def name(cls) -> str:
        """Convert a CamelCase string to snake_case"""
        pattern = re.compile(r"(?<!^)(?=[A-Z])")
        return pattern.sub("_", cls.__name__).lower().replace("_action", "")

    @abstractmethod
    def execution_message(self) -> str:
        """Return the message to be displayed when the action is executed."""
        return f"🚀 Successfully executed action: {self.description}"

    def model_dump_agent(self) -> dict[str, dict[str, Any]]:
        return self.model_dump(exclude=self.non_agent_fields())

    def model_dump_agent_json(self) -> str:
        return json.dumps(self.model_dump(exclude=self.non_agent_fields()))


class BrowserAction(BaseAction, metaclass=ABCMeta):
    """Base model for special actions that are always available and not related to the current page."""

    category: str = "Special Browser Actions"

    BROWSER_ACTION_REGISTRY: ClassVar[dict[str, typeAlias["BrowserAction"]]] = {}

    def __init_subclass__(cls, **kwargs: dict[Any, Any]):
        super().__init_subclass__(**kwargs)

        if not inspect.isabstract(cls):
            name = cls.name()
            if name in cls.BROWSER_ACTION_REGISTRY:
                raise ValueError(f"Base Action {name} is duplicated")
            cls.BROWSER_ACTION_REGISTRY[name] = cls

    @staticmethod
    def is_browser_action(action_type: str) -> bool:
        return action_type in BrowserAction.BROWSER_ACTION_REGISTRY

    @staticmethod
    @abstractmethod
    def example() -> "BrowserAction":
        raise NotImplementedError("This method should be implemented by the subclass")

    @staticmethod
    def list() -> list["BrowserAction"]:
        return [action.example() for action in BrowserAction.BROWSER_ACTION_REGISTRY.values()]

    @property
    @abstractmethod
    def param(self) -> ActionParameter | None:
        raise NotImplementedError("This method should be implemented by the subclass")

    @staticmethod
    def from_param(action_type: str, value: str | int | None = None) -> "BrowserAction":
        if action_type not in BrowserAction.BROWSER_ACTION_REGISTRY:
            raise ValueError(f"Invalid action type: {action_type}")
        action_cls = BrowserAction.BROWSER_ACTION_REGISTRY[action_type]
        param = action_cls.example().param
        action_params = {}
        if param is not None and value is not None:
            action_params[param.name] = value
        return action_cls.model_validate(action_params)


class FormFillAction(BrowserAction):
    type: Literal["form_fill"] = "form_fill"  # pyright: ignore [reportIncompatibleVariableOverride]
    description: str = "Fill a form with multiple values. Critical: If you detect a form on a page, try to use this action at first, and otherwise use the regular fill action"
    value: dict[
        Literal[
            "title",
            "first_name",
            "middle_name",
            "last_name",
            "full_name",
            "email",
            "company",
            "address1",
            "address2",
            "address3",
            "city",
            "state",
            "postal_code",
            "country",
            "phone",
            "cc_name",
            "cc_number",
            "cc_exp_month",
            "cc_exp_year",
            "cc_exp",
            "cc_cvv",
            "username",
            "current_password",
            "new_password",
            "totp",
        ],
        str | ValueWithPlaceholder,
    ]

    @field_validator("value", mode="before")
    @classmethod
    def verify_value(cls, value: Any) -> Any:
        """Validator necessary to ignore typing issues with ValueWithPlaceholder"""
        return value

    @override
    def execution_message(self) -> str:
        return f"Filled the form with the value(s): '{self.value}'"

    @override
    @staticmethod
    def example() -> "FormFillAction":
        return FormFillAction(value={"email": "hello@example.com", "first_name": "Johnny", "last_name": "Smith"})

    @property
    @override
    def param(self) -> ActionParameter | None:
        return ActionParameter(name="value", type="dict")


class GotoAction(BrowserAction):
    type: Literal["goto"] = "goto"  # pyright: ignore [reportIncompatibleVariableOverride]
    description: str = "Goto to a URL (in current tab)"
    url: str

    # Allow 'id' to be a field name
    model_config = {"extra": "forbid", "protected_namespaces": ()}  # type: ignore[reportUnknownMemberType]

    __pydantic_fields_set__ = {"url"}  # type: ignore[reportUnknownMemberType]

    @override
    def execution_message(self) -> str:
        return f"Navigated to '{self.url}' in current tab"

    @override
    @staticmethod
    def example() -> "GotoAction":
        return GotoAction(url="<some_url>")

    @property
    @override
    def param(self) -> ActionParameter | None:
        return ActionParameter(name="url", type="str")


class GotoNewTabAction(BrowserAction):
    type: Literal["goto_new_tab"] = "goto_new_tab"  # pyright: ignore [reportIncompatibleVariableOverride]
    description: str = "Goto to a URL (in new tab)"
    url: str

    @override
    def execution_message(self) -> str:
        return f"Navigated to '{self.url}' in new tab"

    @override
    @staticmethod
    def example() -> "GotoNewTabAction":
        return GotoNewTabAction(url="<some_url>")

    @property
    @override
    def param(self) -> ActionParameter | None:
        return ActionParameter(name="url", type="str")


class SwitchTabAction(BrowserAction):
    type: Literal["switch_tab"] = "switch_tab"  # pyright: ignore [reportIncompatibleVariableOverride]
    description: str = "Switch to a tab (identified by its index)"
    tab_index: int

    @override
    def execution_message(self) -> str:
        return f"Switched to tab {self.tab_index}"

    @override
    @staticmethod
    def example() -> "SwitchTabAction":
        return SwitchTabAction(tab_index=0)

    @property
    @override
    def param(self) -> ActionParameter | None:
        return ActionParameter(name="tab_index", type="int")


class GoBackAction(BrowserAction):
    type: Literal["go_back"] = "go_back"  # pyright: ignore [reportIncompatibleVariableOverride]
    description: str = "Go back to the previous page (in current tab)"

    @override
    def execution_message(self) -> str:
        return "Navigated back to the previous page"

    @override
    @staticmethod
    def example() -> "GoBackAction":
        return GoBackAction()

    @property
    @override
    def param(self) -> ActionParameter | None:
        return None


class GoForwardAction(BrowserAction):
    type: Literal["go_forward"] = "go_forward"  # pyright: ignore [reportIncompatibleVariableOverride]
    description: str = "Go forward to the next page (in current tab)"

    @override
    def execution_message(self) -> str:
        return "Navigated forward to the next page"

    @override
    @staticmethod
    def example() -> "GoForwardAction":
        return GoForwardAction()

    @property
    @override
    def param(self) -> ActionParameter | None:
        return None


class ReloadAction(BrowserAction):
    type: Literal["reload"] = "reload"  # pyright: ignore [reportIncompatibleVariableOverride]
    description: str = "Reload the current page"

    @override
    def execution_message(self) -> str:
        return "Reloaded the current page"

    @override
    @staticmethod
    def example() -> "ReloadAction":
        return ReloadAction()

    @property
    @override
    def param(self) -> ActionParameter | None:
        return None


class WaitAction(BrowserAction):
    type: Literal["wait"] = "wait"  # pyright: ignore [reportIncompatibleVariableOverride]
    description: str = "Wait for a given amount of time (in milliseconds)"
    time_ms: int

    @override
    def execution_message(self) -> str:
        return f"Waited for {self.time_ms} milliseconds"

    @override
    @staticmethod
    def example() -> "WaitAction":
        return WaitAction(time_ms=1000)

    @property
    @override
    def param(self) -> ActionParameter | None:
        return ActionParameter(name="time_ms", type="int")


class PressKeyAction(BrowserAction):
    type: Literal["press_key"] = "press_key"  # pyright: ignore [reportIncompatibleVariableOverride]
    description: str = "Press a keyboard key: e.g. 'Enter', 'Backspace', 'Insert', 'Delete', etc."
    key: str

    @override
    def execution_message(self) -> str:
        return f"Pressed the keyboard key: {self.key}"

    @override
    @staticmethod
    def example() -> "PressKeyAction":
        return PressKeyAction(key="<some_key>")

    @property
    @override
    def param(self) -> ActionParameter | None:
        return ActionParameter(name="key", type="str")


class ScrollUpAction(BrowserAction):
    type: Literal["scroll_up"] = "scroll_up"  # pyright: ignore [reportIncompatibleVariableOverride]
    description: str = "Scroll up by a given amount of pixels. Use `null` for scrolling up one page"
    # amount of pixels to scroll. None for scrolling up one page
    amount: int | None = None

    @override
    def execution_message(self) -> str:
        return f"Scrolled up by {str(self.amount) + ' pixels' if self.amount is not None else 'one page'}"

    @override
    @staticmethod
    def example() -> "ScrollUpAction":
        return ScrollUpAction(amount=None)

    @property
    @override
    def param(self) -> ActionParameter | None:
        return ActionParameter(name="amount", type="int")


class ScrollDownAction(BrowserAction):
    type: Literal["scroll_down"] = "scroll_down"  # pyright: ignore [reportIncompatibleVariableOverride]
    description: str = "Scroll down by a given amount of pixels. Use `null` for scrolling down one page"
    # amount of pixels to scroll. None for scrolling down one page
    amount: int | None = None

    @override
    def execution_message(self) -> str:
        return f"Scrolled down by {str(self.amount) + ' pixels' if self.amount is not None else 'one page'}"

    @override
    @staticmethod
    def example() -> "ScrollDownAction":
        return ScrollDownAction(amount=None)

    @property
    @override
    def param(self) -> ActionParameter | None:
        return ActionParameter(name="amount", type="int")


class CaptchaSolveAction(BrowserAction):
    type: Literal["captcha_solve"] = "captcha_solve"  # pyright: ignore [reportIncompatibleVariableOverride]
    description: str = (
        "Solve a CAPTCHA challenge on the current page. CRITICAL: Use this action as soon as you notice a captcha"
    )
    captcha_type: (
        Literal[
            "recaptcha",
            "hcaptcha",
            "image",
            "text",
            "auth0",
            "cloudflare",
            "datadome",
            "human challenge",
            "arkose labs",
            "geetest",
        ]
        | None
    ) = None  # Optional field to specify the type of CAPTCHA (e.g., 'recaptcha', 'hcaptcha', etc.)

    @override
    def execution_message(self) -> str:
        captcha_desc = f" ({self.captcha_type})" if self.captcha_type else ""
        return f"Solved CAPTCHA challenge{captcha_desc} on the current page"

    @override
    @staticmethod
    def example() -> "CaptchaSolveAction":
        return CaptchaSolveAction(captcha_type="recaptcha")

    @property
    @override
    def param(self) -> ActionParameter | None:
        return ActionParameter(
            name="captcha_type",
            type="str",
            values=[
                "recaptcha",
                "hcaptcha",
                "image",
                "text",
                "cloudflare",
                "datadome",
                "human challenge",
                "arkose labs",
                "geetest",
            ],
        )


# ############################################################
# Special action models
# ############################################################


class HelpAction(BrowserAction):
    type: Literal["help"] = "help"  # pyright: ignore [reportIncompatibleVariableOverride]
    description: str = "Ask for clarification"
    reason: str

    @override
    def execution_message(self) -> str:
        return f"Required help for task: {self.reason}"

    @override
    @staticmethod
    def example() -> "HelpAction":
        return HelpAction(reason="<some_reason>")

    @property
    @override
    def param(self) -> ActionParameter | None:
        return ActionParameter(name="reason", type="str")


class SolveCaptchaAction(BrowserAction):
    type: Literal["solve_captcha"] = "solve_captcha"  # pyright: ignore [reportIncompatibleVariableOverride]
    description: str = "Solve a captcha. IMPORTANT: always use this action if you notice a captcha that needs to be solved on the current page. Try to resolve the captcha type to the best of your ability, but return unknown if you can't"
    captcha_type: Literal[
        "recaptcha",
        "cloudflare_embed",
        "cloudflare_fullpage",
        "perimeterx",
        "human_security",
        "akamai",
        "datadome",
        "imperva",
        "aws_waf",
        "kasada",
        "geetest",
        "funcaptcha",
        "unknown",
    ]

    @override
    def execution_message(self) -> str:
        return "Solved captcha"

    @override
    @staticmethod
    def example() -> "SolveCaptchaAction":
        return SolveCaptchaAction(captcha_type="cloudflare_fullpage")

    @property
    @override
    def param(self) -> ActionParameter | None:
        return None


class CompletionAction(BrowserAction):
    type: Literal["completion"] = "completion"  # pyright: ignore [reportIncompatibleVariableOverride]
    description: str = "Complete the task by returning the answer and terminate the browser session"
    success: bool
    answer: str

    # useful because models like to output as dict when giving expected basemodel
    @field_validator("answer", mode="before")
    @classmethod
    def convert_dict_to_json(cls, value: Any) -> str:
        if isinstance(value, dict):
            return json.dumps(value)
        return value

    @override
    def execution_message(self) -> str:
        return f"Completed the task with success: {self.success} and answer: {self.answer}"

    @override
    @staticmethod
    def example() -> "CompletionAction":
        return CompletionAction(success=True, answer="<some_answer>")

    @property
    @override
    def param(self) -> ActionParameter | None:
        return ActionParameter(name="answer", type="str")


# ############################################################
# Data action models
# ############################################################


class ToolAction(BrowserAction, metaclass=ABCMeta):
    type: Literal["data"] = "data"  # pyright: ignore [reportIncompatibleVariableOverride]


class ScrapeAction(ToolAction):
    type: Literal["scrape"] = "scrape"  # pyright: ignore [reportIncompatibleVariableOverride]
    description: str = (
        "Scrape the current page data in text format. "
        "If `instructions` is null then the whole page will be scraped. "
        "Otherwise, only the data that matches the instructions will be scraped. "
        "Instructions should be given as natural language, e.g. 'Extract the title and the price of the product'"
    )
    instructions: str | None = None
    only_main_content: Annotated[
        bool,
        Field(
            description="Whether to only scrape the main content of the page. If True, navbars, footers, etc. are excluded."
        ),
    ] = True

    @override
    def execution_message(self) -> str:
        if self.only_main_content:
            content = "main content of the current page"
        else:
            content = "current page"

        if self.instructions:
            instructions = f" with instructions '{self.instructions}'"
        else:
            instructions = ""

        return f"Scraped the {content} in text format{instructions}"

    @override
    @staticmethod
    def example() -> "ScrapeAction":
        return ScrapeAction(instructions="<some_instructions>")

    @property
    @override
    def param(self) -> ActionParameter | None:
        return ActionParameter(name="instructions", type="str")


# #########################################################
# ################### PERSONA ACTIONS #####################
# #########################################################
class EmailReadAction(ToolAction):
    type: Literal["email_read"] = "email_read"  # pyright: ignore [reportIncompatibleVariableOverride]
    description: str = "Read recent emails from the mailbox."
    limit: Annotated[int, Field(description="Max number of emails to return")] = 10
    timedelta: Annotated[
        dt.timedelta | None, Field(description="Return only emails that are not older than <timedelta>")
    ] = dt.timedelta(minutes=5)
    only_unread: Annotated[bool, Field(description="Return only previously unread emails")] = True

    @override
    def execution_message(self) -> str:
        if self.timedelta is None:
            return "Successfully read emails from the inbox"
        else:
            return f"Successfully read emails from the inbox in the last {self.timedelta}"

    @override
    @staticmethod
    def example() -> "EmailReadAction":
        return EmailReadAction(
            timedelta=dt.timedelta(minutes=5),
            only_unread=True,
        )

    @property
    @override
    def param(self) -> ActionParameter | None:
        return ActionParameter(name="timedelta", type="datetime")


class SmsReadAction(ToolAction):
    type: Literal["sms_read"] = "sms_read"  # pyright: ignore [reportIncompatibleVariableOverride]
    description: str = "Read sms messages recieved recently."
    limit: Annotated[int, Field(description="Max number of sms to return")] = 10
    timedelta: Annotated[
        dt.timedelta | None, Field(description="Return only sms that are not older than <timedelta>")
    ] = dt.timedelta(minutes=5)
    only_unread: Annotated[bool, Field(description="Return only previously unread sms")] = True

    @override
    def execution_message(self) -> str:
        if self.timedelta is None:
            return "Successfully read sms messages from the inbox"
        else:
            return f"Successfully read sms messages from the inbox in the last {self.timedelta}"

    @override
    @staticmethod
    def example() -> "SmsReadAction":
        return SmsReadAction(
            timedelta=dt.timedelta(minutes=5),
            only_unread=True,
        )

    @property
    @override
    def param(self) -> ActionParameter | None:
        return ActionParameter(name="timedelta", type="datetime")


# ############################################################
# Interaction actions models
# ############################################################


class InteractionAction(BaseAction, metaclass=ABCMeta):
    id: str  # pyright: ignore [reportIncompatibleMethodOverride]
    selector: NodeSelectors | None = Field(default=None)
    category: str = Field(default="Interaction Actions", min_length=1)
    press_enter: bool | None = Field(default=None)
    text_label: str | None = Field(default=None)
    param: ActionParameter | None = Field(default=None, exclude=True)

    INTERACTION_ACTION_REGISTRY: ClassVar[dict[str, typeAlias["InteractionAction"]]] = {}

    @field_validator("id", mode="before")
    @classmethod
    def cleanup_id(cls, value: str) -> str:
        if value.endswith("[:]"):
            return value[:-3]
        return value

    def __init_subclass__(cls, **kwargs: dict[Any, Any]):
        super().__init_subclass__(**kwargs)

        if not inspect.isabstract(cls):
            name = cls.name()
            if name in cls.INTERACTION_ACTION_REGISTRY:
                raise ValueError(f"Base Action {name} is duplicated")
            cls.INTERACTION_ACTION_REGISTRY[name] = cls

    @staticmethod
    def from_param(
        action_type: str,
        value: bool | str | int | None = None,
        action_id: str | None = None,
        selector: str | NodeSelectors | None = None,
    ) -> "InteractionAction":
        action_cls = InteractionAction.INTERACTION_ACTION_REGISTRY.get(action_type)
        if action_cls is None:
            raise ValueError(f"Invalid action type: {action_type}")

        action_params: dict[str, Any] = {"id": action_id or ""}
        if value is not None:
            action_params["value"] = value

        action = action_cls.model_validate(action_params)

        # have to assume simple playwright selector in this case
        # could maybe dispatch?
        if selector is not None:
            if isinstance(selector, str):
                action.selector = NodeSelectors(
                    playwright_selector=selector,
                    css_selector="",
                    xpath_selector="",
                    notte_selector="",
                    in_iframe=False,
                    in_shadow_root=False,
                    iframe_parent_css_selectors=[],
                )
            elif isinstance(selector, NodeSelectors):  # pyright: ignore [reportUnnecessaryIsInstance]
                action.selector = selector
            else:
                raise ValueError(f"Invalid selector type: {type(selector)}")  # pyright: ignore [reportUnreachable]
        return action


class ClickAction(InteractionAction):
    type: Literal["click"] = "click"  # pyright: ignore [reportIncompatibleVariableOverride]
    description: str = "Click on an element of the current page"

    @override
    def execution_message(self) -> str:
        if self.text_label is None or len(self.text_label) == 0:
            return "Clicked on element"
        return f"Clicked on the element with text label: {self.text_label}"


class FillAction(InteractionAction):
    type: Literal["fill"] = "fill"  # pyright: ignore [reportIncompatibleVariableOverride]
    description: str = "Fill an input field with a value"
    value: str | ValueWithPlaceholder
    clear_before_fill: bool = True
    param: ActionParameter | None = Field(default=ActionParameter(name="value", type="str"), exclude=True)

    @field_validator("value", mode="before")
    @classmethod
    def verify_value(cls, value: Any) -> Any:
        """Validator necessary to ignore typing issues with ValueWithPlaceholder"""
        return value

    @override
    def execution_message(self) -> str:
        return f"Filled the input field '{self.text_label}' with the value: '{self.value}'"


class MultiFactorFillAction(InteractionAction):
    type: Literal["multi_factor_fill"] = "multi_factor_fill"  # pyright: ignore [reportIncompatibleVariableOverride]
    description: str = "Fill an MFA input field with a value. CRITICAL: Only use it when filling in an OTP."
    value: str | ValueWithPlaceholder
    clear_before_fill: bool = True
    param: ActionParameter | None = Field(default=ActionParameter(name="value", type="str"), exclude=True)

    @field_validator("value", mode="before")
    @classmethod
    def verify_value(cls, value: Any) -> Any:
        """Validator necessary to ignore typing issues with ValueWithPlaceholder"""
        return value

    @override
    def execution_message(self) -> str:
        return f"Filled the MFA input field with the value: '{self.value}'"


class FallbackFillAction(InteractionAction):
    type: Literal["fallback_fill"] = "fallback_fill"  # pyright: ignore [reportIncompatibleVariableOverride]
    description: str = "Fill an input field with a value. Only use if explicitly asked, or you failed to input with the normal fill action"
    value: str | ValueWithPlaceholder
    clear_before_fill: bool = True
    param: ActionParameter | None = Field(default=ActionParameter(name="value", type="str"), exclude=True)

    @field_validator("value", mode="before")
    @classmethod
    def verify_value(cls, value: Any) -> Any:
        """Validator necessary to ignore typing issues with ValueWithPlaceholder"""
        return value

    @override
    def execution_message(self) -> str:
        return f"Filled (fallback) the input field '{self.text_label}' with the value: '{self.value}'"


class CheckAction(InteractionAction):
    type: Literal["check"] = "check"  # pyright: ignore [reportIncompatibleVariableOverride]
    description: str = "Check a checkbox. Use `True` to check, `False` to uncheck"
    value: bool
    param: ActionParameter | None = Field(default=ActionParameter(name="value", type="bool"), exclude=True)

    @override
    def execution_message(self) -> str:
        return f"Checked the checkbox '{self.text_label}'" if self.text_label is not None else "Checked the checkbox"


# class ListDropdownOptionsAction(InteractionAction):
#     id: str
#     description: str = "List all options of a dropdown"
#
#     @override
#     def execution_message(self) -> str:
#         return (
#             f"Listed all options of the dropdown '{self.text_label}'"
#             if self.text_label is not None
#             else "Listed all options of the dropdown"
#         )


class SelectDropdownOptionAction(InteractionAction):
    type: Literal["select_dropdown_option"] = "select_dropdown_option"  # pyright: ignore [reportIncompatibleVariableOverride]
    description: str = (
        "Select an option from a dropdown. The `id` field should be set to the select element's id. "
        "Then you can either set the `value` field to the option's text or the `option_id` field to the option's `id`."
    )
    value: str | ValueWithPlaceholder
    param: ActionParameter | None = Field(default=ActionParameter(name="value", type="str"), exclude=True)

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


class UploadFileAction(InteractionAction):
    type: Literal["upload_file"] = "upload_file"  # pyright: ignore [reportIncompatibleVariableOverride]
    description: str = (
        "Upload file to interactive element with file path. "
        "Use with any upload file element, including button, input, a, span, div. "
        "CRITICAL: Use only this for file upload, do not use click."
    )
    file_path: str
    param: ActionParameter | None = Field(default=ActionParameter(name="file_path", type="str"), exclude=True)

    @override
    def execution_message(self) -> str:
        return f"Uploaded the file '{self.file_path}' to the current page"


class DownloadFileAction(InteractionAction):
    type: Literal["download_file"] = "download_file"  # pyright: ignore [reportIncompatibleVariableOverride]
    description: str = (
        "Download files from interactive elements. "
        "Use with any clickable download file element, including button, a, span, div. "
        "CRITICAL: Use only this for file download, do not use click."
    )

    @override
    def execution_message(self) -> str:
        return f"Downloaded the file from element with text label: {self.text_label}"


# ############################################################
# Action Union Models
# ############################################################


BrowserActionUnion = Annotated[
    reduce(operator.or_, BrowserAction.BROWSER_ACTION_REGISTRY.values()), Field(discriminator="type")
]
InteractionActionUnion = Annotated[
    reduce(operator.or_, InteractionAction.INTERACTION_ACTION_REGISTRY.values()), Field(discriminator="type")
]
ActionUnion = Annotated[reduce(operator.or_, BaseAction.ACTION_REGISTRY.values()), Field(discriminator="type")]


class ActionValidation(BaseModel):
    action: ActionUnion


class ActionList(BaseModel):
    actions: list[ActionUnion]
