import datetime as dt
import inspect
import json
import operator
import re
import warnings
from abc import ABCMeta, abstractmethod
from functools import reduce
from typing import Annotated, Any, ClassVar, Literal, get_args

from pydantic import BaseModel, Field, field_validator, model_validator
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
            "param",
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

    def model_dump_agent(self, include_selector: bool = False) -> dict[str, dict[str, Any]]:
        fields = self.non_agent_fields()
        if include_selector and "selector" in fields:
            fields.remove("selector")
            fields.add("id")
        data = self.model_dump(exclude=fields)
        selector = data.get("selector")
        if selector:
            data["selector"] = selector["playwright_selector"] or selector["xpath_selector"]
        return data

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
    """
    Fill a form with multiple values. Critical: If you detect a form on a page, try to use this action at first, and otherwise use the regular fill action.

    **Example:**
    ```python
    from notte_core.actions import FormFillAction
    # Dict syntax
    session.execute({
        "type": "form_fill",
        "value": {"email": "user@example.com", "first_name": "John", "last_name": "Doe"}
    })
    # Pydantic syntax
    session.execute(FormFillAction(value={"email": "user@example.com", "first_name": "John", "last_name": "Doe"}))
    ```
    """

    type: Literal["form_fill"] = "form_fill"  # pyright: ignore [reportIncompatibleVariableOverride]
    description: str = "Fill a form with multiple values. Important: If you detect a form requesting personal information, try to use this action at first, and otherwise use the regular fill action. CRITICAL: If this action fails once, use the regular form fill instead."
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
    ] = Field(min_length=1)

    @field_validator("value", mode="before")
    @classmethod
    def verify_value(cls, value: Any) -> Any:
        """Validator necessary to ignore typing issues with ValueWithPlaceholder"""
        if value is None:
            allowed_keys = get_args(get_args(cls.model_fields["value"].annotation)[0])
            raise ValueError(
                f"'value' key in form fill action has to be an object with at least one key among {allowed_keys}, but got {value}. CRITICAL: fall back to the regular fill action"
            )
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
    """
    Goto to a URL (in current tab).

    **Example:**
    ```python
    from notte_core.actions import GotoAction
    # Dict syntax
    session.execute({"type": "goto", "url": "https://www.google.com"})
    # Pydantic syntax
    session.execute(GotoAction(url="https://www.google.com"))
    ```
    """

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
    """
    Goto to a URL (in new tab).

    **Example:**
    ```python
    from notte_core.actions import GotoNewTabAction
    # Dict syntax
    session.execute({"type": "goto_new_tab", "url": "https://www.example.com"})
    # Pydantic syntax
    session.execute(GotoNewTabAction(url="https://www.example.com"))
    ```
    """

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


class CloseTabAction(BrowserAction):
    """
    Close the current tab.
    """

    type: Literal["close_tab"] = "close_tab"  # pyright: ignore [reportIncompatibleVariableOverride]
    description: str = "Close the current tab"

    @override
    def execution_message(self) -> str:
        return "Closed the current tab"

    @override
    @staticmethod
    def example() -> "CloseTabAction":
        return CloseTabAction()

    @property
    @override
    def param(self) -> ActionParameter | None:
        return None


class SwitchTabAction(BrowserAction):
    """
    Switch to a tab (identified by its index).

    **Example:**
    ```python
    from notte_core.actions import SwitchTabAction
    # Dict syntax
    session.execute({"type": "switch_tab", "tab_index": 1})
    # Pydantic syntax
    session.execute(SwitchTabAction(tab_index=1))
    ```
    """

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
    """
    Go back to the previous page (in current tab).

    **Example:**
    ```python
    from notte_core.actions import GoBackAction
    # Dict syntax
    session.execute({"type": "go_back"})
    # Pydantic syntax
    session.execute(GoBackAction())
    ```
    """

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
    """
    Go forward to the next page (in current tab).

    **Example:**
    ```python
    from notte_core.actions import GoForwardAction
    # Dict syntax
    session.execute({"type": "go_forward"})
    # Pydantic syntax
    session.execute(GoForwardAction())
    ```
    """

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
    """
    Reload the current page.

    **Example:**
    ```python
    from notte_core.actions import ReloadAction
    # Dict syntax
    session.execute({"type": "reload"})
    # Pydantic syntax
    session.execute(ReloadAction())
    ```
    """

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
    """
    Wait for a given amount of time (in milliseconds).

    **Example:**
    ```python
    from notte_core.actions import WaitAction
    # Dict syntax
    session.execute({"type": "wait", "time_ms": 2000})
    # Pydantic syntax
    session.execute(WaitAction(time_ms=2000))
    ```
    """

    type: Literal["wait"] = "wait"  # pyright: ignore [reportIncompatibleVariableOverride]
    description: str = "Wait for a given amount of time (in milliseconds)"
    time_ms: Annotated[
        int, Field(ge=0, le=30000, description="The amount of time to wait in milliseconds (max 30 seconds)")
    ]

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
    """
    Press a keyboard key: e.g. 'Enter', 'Backspace', 'Insert', 'Delete', etc.

    **Example:**
    ```python
    from notte_core.actions import PressKeyAction
    # Dict syntax
    session.execute({"type": "press_key", "key": "Enter"})
    # Pydantic syntax
    session.execute(PressKeyAction(key="Enter"))
    ```
    """

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
    """
    Scroll up by a given amount of pixels. Use `None` for scrolling up one page.

    **Example:**
    ```python
    from notte_core.actions import ScrollUpAction
    # Dict syntax
    session.execute({"type": "scroll_up", "amount": 500})  # Scroll up 500 pixels
    session.execute({"type": "scroll_up"})  # Scroll up one page
    # Pydantic syntax
    session.execute(ScrollUpAction(amount=500))
    session.execute(ScrollUpAction(amount=None))
    ```
    """

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
    """
    Scroll down by a given amount of pixels. Use `null` for scrolling down one page.

    **Example:**
    ```python
    from notte_core.actions import ScrollDownAction
    # Dict syntax
    session.execute({"type": "scroll_down", "amount": 500})  # Scroll down 500 pixels
    session.execute({"type": "scroll_down"})  # Scroll down one page
    # Pydantic syntax
    session.execute(ScrollDownAction(amount=500))
    session.execute(ScrollDownAction(amount=None))
    ```
    """

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
    """
    Solve a CAPTCHA challenge on the current page. CRITICAL: Use this action as soon as you notice a captcha.

    **Example:**
    ```python
    from notte_core.actions import CaptchaSolveAction
    # Dict syntax
    session.execute({"type": "captcha_solve", "captcha_type": "recaptcha"})
    session.execute({"type": "captcha_solve"})  # Auto-detect captcha type
    # Pydantic syntax
    session.execute(CaptchaSolveAction(captcha_type="recaptcha"))
    session.execute(CaptchaSolveAction())
    ```
    """

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
            "arkose labs",
            "geetest",
            "press&hold",
            "unknown",
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
                "auth0",
                "cloudflare",
                "datadome",
                "arkose labs",
                "geetest",
                "press&hold",
                "unknown",
            ],
        )


# ############################################################
# Special action models
# ############################################################


class HelpAction(BrowserAction):
    """
    Ask for clarification.

    **Example:**
    ```python
    from notte_core.actions import HelpAction
    # Dict syntax
    session.execute({"type": "help", "reason": "The page layout is unclear"})
    # Pydantic syntax
    session.execute(HelpAction(reason="The page layout is unclear"))
    ```
    """

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


class CompletionAction(BrowserAction):
    """
    Complete the task by returning the answer and terminate the browser session.

    **Example:**
    ```python
    from notte_core.actions import CompletionAction
    # Dict syntax
    session.execute({"type": "completion", "success": True, "answer": "Task completed successfully"})
    session.execute({"type": "completion", "success": False, "answer": "Could not complete task"})
    # Pydantic syntax
    session.execute(CompletionAction(success=True, answer="Task completed successfully"))
    session.execute(CompletionAction(success=False, answer="Could not complete task"))
    ```
    """

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
    """
    Scrape the current page data in text format. If `instructions` is null then the whole page will be scraped. Otherwise, only the data that matches the instructions will be scraped. Instructions should be given as natural language, e.g. 'Extract the title and the price of the product'.

    **Example:**
    ```python
    from notte_core.actions import ScrapeAction
    # Dict syntax
    session.execute({"type": "scrape", "instructions": "Extract product title and price"})
    session.execute({"type": "scrape", "only_main_content": True})
    session.execute({"type": "scrape"})  # Scrape entire page
    # Pydantic syntax
    session.execute(ScrapeAction(instructions="Extract product title and price"))
    session.execute(ScrapeAction(only_main_content=True))
    session.execute(ScrapeAction())
    ```
    """

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
    """
    Read recent emails from the mailbox.

    **Example:**
    ```python
    import datetime as dt
    from notte_core.actions import EmailReadAction
    # Dict syntax
    session.execute({"type": "email_read", "limit": 5, "only_unread": True})
    session.execute({"type": "email_read", "timedelta": "PT5M"})  # Last 5 minutes
    # Pydantic syntax
    session.execute(EmailReadAction(limit=5, only_unread=True))
    session.execute(EmailReadAction(timedelta=dt.timedelta(minutes=5)))
    ```
    """

    type: Literal["email_read"] = "email_read"  # pyright: ignore [reportIncompatibleVariableOverride]
    description: str = "Read recent emails from the mailbox."
    limit: Annotated[int, Field(description="Max number of emails to return")] = 10
    timedelta: Annotated[
        dt.timedelta | None, Field(description="Return only emails that are not older than `timedelta`")
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
    """
    Read sms messages received recently.

    **Example:**
    ```python
    import datetime as dt
    from notte_core.actions import SmsReadAction
    # Dict syntax
    session.execute({"type": "sms_read", "limit": 10, "only_unread": True})
    session.execute({"type": "sms_read", "timedelta": "PT5M"})  # Last 5 minutes
    # Pydantic syntax
    session.execute(SmsReadAction(limit=10, only_unread=True))
    session.execute(SmsReadAction(timedelta=dt.timedelta(minutes=5)))
    ```
    """

    type: Literal["sms_read"] = "sms_read"  # pyright: ignore [reportIncompatibleVariableOverride]
    description: str = "Read sms messages received recently."
    limit: Annotated[int, Field(description="Max number of sms to return")] = 10
    timedelta: Annotated[
        dt.timedelta | None, Field(description="Return only sms that are not older than `timedelta`")
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
    id: str
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

    @model_validator(mode="before")
    @classmethod
    def validate_id_and_selector(cls, data: Any) -> Any:
        id = data.get("id")
        selector = data.get("selector")
        if id is None and selector is None:
            raise ValueError(
                f"{data.get('type') or 'interaction'} action need to provide either an action id or a selector"
            )
        if id is None and selector is not None:
            data["id"] = ""
        return data

    def __init_subclass__(cls, **kwargs: dict[Any, Any]):
        super().__init_subclass__(**kwargs)

        if not inspect.isabstract(cls):
            name = cls.name()
            if name in cls.INTERACTION_ACTION_REGISTRY:
                raise ValueError(f"Base Action {name} is duplicated")
            cls.INTERACTION_ACTION_REGISTRY[name] = cls

    # @field_serializer("selector")
    # def serialize_selector(self, selector: NodeSelectors | None, _info: Any) -> str | None:
    #     if selector is None:
    #         return None
    #     return selector.selectors()[0]

    @field_validator("selector", mode="before")
    @classmethod
    def validate_selector(cls, value: str | NodeSelectors | None) -> NodeSelectors | None:
        if isinstance(value, str):
            return NodeSelectors.from_unique_selector(value)
        return value

    @staticmethod
    def from_param(
        action_type: str,
        value: bool | str | int | None = None,
        id: str | None = None,
        selector: str | NodeSelectors | None = None,
    ) -> "InteractionAction":
        action_cls = InteractionAction.INTERACTION_ACTION_REGISTRY.get(action_type)
        if action_cls is None:
            raise ValueError(f"Invalid action type: {action_type}")

        action_params: dict[str, Any] = {"id": id or ""}
        if value is not None:
            action_params["value"] = value

        action = action_cls.model_validate(action_params)

        # have to assume simple playwright selector in this case
        # could maybe dispatch?
        if selector is not None:
            if isinstance(selector, str):
                action.selector = NodeSelectors.from_unique_selector(selector)
            elif isinstance(selector, NodeSelectors):  # pyright: ignore [reportUnnecessaryIsInstance]
                action.selector = selector
            else:
                raise ValueError(f"Invalid selector type: {type(selector)}")  # pyright: ignore [reportUnreachable]
        return action


class ClickAction(InteractionAction):
    """
    Click on an element of the current page.

    **Example:**
    ```python
    from notte_core.actions import ClickAction
    # Dict syntax
    session.execute({"type": "click", "id": "submit-button"})
    # Pydantic syntax
    session.execute(ClickAction(id="submit-button"))
    ```
    """

    type: Literal["click"] = "click"  # pyright: ignore [reportIncompatibleVariableOverride]
    description: str = "Click on an element of the current page"

    @override
    def execution_message(self) -> str:
        if self.text_label is None or len(self.text_label) == 0:
            return "Clicked on element"
        return f"Clicked on the element with text label: {self.text_label}"


class FillAction(InteractionAction):
    """
    Fill an input field with a value.

    **Example:**
    ```python
    from notte_core.actions import FillAction
    # Dict syntax
    session.execute({"type": "fill", "id": "email-input", "value": "user@example.com"})
    session.execute({"type": "fill", "id": "name-input", "value": "John Doe", "clear_before_fill": False})
    # Pydantic syntax
    session.execute(FillAction(id="email-input", value="user@example.com"))
    session.execute(FillAction(id="name-input", value="John Doe", clear_before_fill=False))
    ```
    """

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
        text_label = f" '{self.text_label}' " if self.text_label else " "
        return f"Filled input field{text_label}with the value: '{self.value}'"


class MultiFactorFillAction(InteractionAction):
    """
    Fill an MFA input field with a value. CRITICAL: Only use it when filling in an OTP.

    **Example:**
    ```python
    from notte_core.actions import MultiFactorFillAction
    # Dict syntax
    session.execute({"type": "multi_factor_fill", "id": "otp-input", "value": "123456"})
    # Pydantic syntax
    session.execute(MultiFactorFillAction(id="otp-input", value="123456"))
    ```
    """

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
    """
    Fill an input field with a value. Only use if explicitly asked, or you failed to input with the normal fill action.

    **Example:**
    ```python
    from notte_core.actions import FallbackFillAction
    # Dict syntax
    session.execute({"type": "fallback_fill", "id": "difficult-input", "value": "fallback text"})
    # Pydantic syntax
    session.execute(FallbackFillAction(id="difficult-input", value="fallback text"))
    ```
    """

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
    """
    Check a checkbox. Use `True` to check, `False` to uncheck.

    **Example:**
    ```python
    from notte_core.actions import CheckAction
    # Dict syntax
    session.execute({"type": "check", "id": "terms-checkbox", "value": True})
    session.execute({"type": "check", "id": "newsletter-checkbox", "value": False})
    # Pydantic syntax
    session.execute(CheckAction(id="terms-checkbox", value=True))
    session.execute(CheckAction(id="newsletter-checkbox", value=False))
    ```
    """

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
    """
    Select an option from a dropdown. The `id` field should be set to the select element's id. Then you can either set the `value` field to the option's text or the `option_id` field to the option's `id`.

    **Example:**
    ```python
    from notte_core.actions import SelectDropdownOptionAction
    # Dict syntax
    session.execute({"type": "select_dropdown_option", "id": "country-select", "value": "United States"})
    session.execute({"type": "select_dropdown_option", "id": "size-select", "value": "Large"})
    # Pydantic syntax
    session.execute(SelectDropdownOptionAction(id="country-select", value="United States"))
    session.execute(SelectDropdownOptionAction(id="size-select", value="Large"))
    ```
    """

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
    """
    Upload file to interactive element with file path. Use with any upload file element, including button, input, a, span, div. CRITICAL: Use only this for file upload, do not use click.

    **Example:**
    ```python
    from notte_core.actions import UploadFileAction
    # Dict syntax
    session.execute({"type": "upload_file", "id": "file-input", "file_path": "/path/to/document.pdf"})
    session.execute({"type": "upload_file", "id": "image-upload", "file_path": "./image.jpg"})
    # Pydantic syntax
    session.execute(UploadFileAction(id="file-input", file_path="/path/to/document.pdf"))
    session.execute(UploadFileAction(id="image-upload", file_path="./image.jpg"))
    ```
    """

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
    """
    Download files from interactive elements. Use with any clickable download file element, including button, a, span, div. CRITICAL: Use only this for file download, do not use click.

    **Example:**
    ```python
    from notte_core.actions import DownloadFileAction
    # Dict syntax
    session.execute({"type": "download_file", "id": "download-button"})
    session.execute({"type": "download_file", "id": "report-link"})
    # Pydantic syntax
    session.execute(DownloadFileAction(id="download-button"))
    session.execute(DownloadFileAction(id="report-link"))
    ```
    """

    type: Literal["download_file"] = "download_file"  # pyright: ignore [reportIncompatibleVariableOverride]
    description: str = (
        "Download files from interactive elements. "
        "Use with any clickable element which triggers a download, including button, a, div. "
        "This action can also be used to download pages which are raw files (ex. PDF viewer). "
        "CRITICAL: Use only this for file download, DO NOT use click."
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
