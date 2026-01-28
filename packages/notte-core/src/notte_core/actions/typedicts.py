"""
TypedDict definitions for all action types.

This module provides TypedDict definitions for each action type to enable
type-safe keyword argument passing to execute methods.
"""

import datetime as dt
from typing import TYPE_CHECKING, Any, Literal, NotRequired, Required, TypedDict

from notte_core.actions.actions import ActionUnion
from notte_core.browser.dom_tree import NodeSelectors
from notte_core.credentials.types import ValueWithPlaceholder

if TYPE_CHECKING:
    from notte_core.actions.actions import BaseAction

# All action types as a Literal union for catch-all overloads
ActionType = Literal[
    "form_fill",
    "goto",
    "goto_new_tab",
    "close_tab",
    "switch_tab",
    "go_back",
    "go_forward",
    "reload",
    "wait",
    "press_key",
    "scroll_up",
    "scroll_down",
    "captcha_solve",
    "help",
    "completion",
    "scrape",
    "email_read",
    "sms_read",
    "click",
    "fill",
    "multi_factor_fill",
    "fallback_fill",
    "check",
    "select_dropdown_option",
    "upload_file",
    "download_file",
]

# Browser Actions TypedDicts


class FormFillActionDict(TypedDict, total=False):
    type: Required[Literal["form_fill"]]
    value: Required[
        dict[
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
    ]


class GotoActionDict(TypedDict):
    type: Literal["goto"]
    url: str


class GotoNewTabActionDict(TypedDict):
    type: Literal["goto_new_tab"]
    url: str


class CloseTabActionDict(TypedDict):
    type: Literal["close_tab"]


class SwitchTabActionDict(TypedDict):
    type: Literal["switch_tab"]
    tab_index: int


class GoBackActionDict(TypedDict):
    type: Literal["go_back"]


class GoForwardActionDict(TypedDict):
    type: Literal["go_forward"]


class ReloadActionDict(TypedDict):
    type: Literal["reload"]


class WaitActionDict(TypedDict):
    type: Literal["wait"]
    time_ms: int


class PressKeyActionDict(TypedDict):
    type: Literal["press_key"]
    key: str


class ScrollUpActionDict(TypedDict, total=False):
    type: Required[Literal["scroll_up"]]
    amount: NotRequired[int | None]


class ScrollDownActionDict(TypedDict, total=False):
    type: Required[Literal["scroll_down"]]
    amount: NotRequired[int | None]


class CaptchaSolveActionDict(TypedDict, total=False):
    type: Required[Literal["captcha_solve"]]
    captcha_type: NotRequired[
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
    ]


class HelpActionDict(TypedDict):
    type: Literal["help"]
    reason: str


class CompletionActionDict(TypedDict):
    type: Literal["completion"]
    success: bool
    answer: str


class ScrapeActionDict(TypedDict, total=False):
    type: Required[Literal["scrape"]]
    instructions: NotRequired[str | None]
    only_main_content: NotRequired[bool]
    selector: NotRequired[str | None]
    only_images: NotRequired[bool]
    scrape_links: NotRequired[bool]
    scrape_images: NotRequired[bool]
    ignored_tags: NotRequired[list[str] | None]
    response_format: NotRequired[dict[str, Any] | None]


class EmailReadActionDict(TypedDict, total=False):
    type: Required[Literal["email_read"]]
    limit: NotRequired[int]
    timedelta: NotRequired[dt.timedelta | None]
    only_unread: NotRequired[bool]


class SmsReadActionDict(TypedDict, total=False):
    type: Required[Literal["sms_read"]]
    limit: NotRequired[int]
    timedelta: NotRequired[dt.timedelta | None]
    only_unread: NotRequired[bool]


# Interaction Actions TypedDicts


class ClickActionDict(TypedDict, total=False):
    type: Required[Literal["click"]]
    id: NotRequired[str]
    selector: NotRequired[str | NodeSelectors]
    timeout: NotRequired[int]


class FillActionDict(TypedDict, total=False):
    type: Required[Literal["fill"]]
    id: NotRequired[str]
    selector: NotRequired[str | NodeSelectors]
    value: Required[str | ValueWithPlaceholder]
    clear_before_fill: NotRequired[bool]
    timeout: NotRequired[int]


class MultiFactorFillActionDict(TypedDict, total=False):
    type: Required[Literal["multi_factor_fill"]]
    id: NotRequired[str]
    selector: NotRequired[str | NodeSelectors]
    value: Required[str | ValueWithPlaceholder]
    clear_before_fill: NotRequired[bool]
    timeout: NotRequired[int]


class FallbackFillActionDict(TypedDict, total=False):
    type: Required[Literal["fallback_fill"]]
    id: NotRequired[str]
    selector: NotRequired[str | NodeSelectors]
    value: Required[str | ValueWithPlaceholder]
    clear_before_fill: NotRequired[bool]
    timeout: NotRequired[int]


class CheckActionDict(TypedDict, total=False):
    type: Required[Literal["check"]]
    id: NotRequired[str]
    selector: NotRequired[str | NodeSelectors]
    value: Required[bool]
    timeout: NotRequired[int]


class SelectDropdownOptionActionDict(TypedDict, total=False):
    type: Required[Literal["select_dropdown_option"]]
    id: NotRequired[str]
    selector: NotRequired[str | NodeSelectors]
    value: Required[str | ValueWithPlaceholder]
    timeout: NotRequired[int]


class UploadFileActionDict(TypedDict, total=False):
    type: Required[Literal["upload_file"]]
    id: NotRequired[str]
    selector: NotRequired[str | NodeSelectors]
    file_path: Required[str]
    timeout: NotRequired[int]


class DownloadFileActionDict(TypedDict, total=False):
    type: Required[Literal["download_file"]]
    id: NotRequired[str]
    selector: NotRequired[str | NodeSelectors]
    timeout: NotRequired[int]


# Union type for all action TypedDicts
ActionDict = (
    FormFillActionDict
    | GotoActionDict
    | GotoNewTabActionDict
    | CloseTabActionDict
    | SwitchTabActionDict
    | GoBackActionDict
    | GoForwardActionDict
    | ReloadActionDict
    | WaitActionDict
    | PressKeyActionDict
    | ScrollUpActionDict
    | ScrollDownActionDict
    | CaptchaSolveActionDict
    | HelpActionDict
    | CompletionActionDict
    | ScrapeActionDict
    | EmailReadActionDict
    | SmsReadActionDict
    | ClickActionDict
    | FillActionDict
    | MultiFactorFillActionDict
    | FallbackFillActionDict
    | CheckActionDict
    | SelectDropdownOptionActionDict
    | UploadFileActionDict
    | DownloadFileActionDict
)


def action_dict_to_base_action(data: ActionDict) -> "BaseAction":
    """
    Fast mapping from action TypedDict to BaseAction instance.

    This function uses the ACTION_REGISTRY to quickly map keyword arguments
    to the appropriate BaseAction subclass without going through Pydantic
    validation overhead where possible.

    Supports backward compatibility with the deprecated `value` parameter,
    which is transformed to the action-specific parameter name (e.g., `url` for goto).
    """
    import logging
    import warnings

    from notte_core.actions.actions import (
        ActionValidation,
        BaseAction,
        BrowserAction,
        InteractionAction,
    )

    logger = logging.getLogger(__name__)

    try:
        action_type = data["type"]
    except KeyError as e:
        raise ValueError("Missing required action field: 'type'") from e

    # Backward compatibility: transform deprecated `value` parameter to action-specific field
    if "value" in data and action_type in BaseAction.ACTION_REGISTRY:
        action_cls = BaseAction.ACTION_REGISTRY[action_type]

        # Check if this action class has a `param` property that defines the expected field name
        if issubclass(action_cls, BrowserAction):
            # Get the param from the example instance
            param = action_cls.example().param
            if param is not None and param.name != "value":
                # Transform `value` to the correct field name
                mutable_data = dict(data)
                mutable_data[param.name] = mutable_data.pop("value")
                data = mutable_data  # type: ignore[assignment]

                warnings.warn(
                    f"Using 'value' parameter for '{action_type}' action is deprecated. "
                    + f"Use '{param.name}' instead. Example: execute(type='{action_type}', {param.name}=...)",
                    DeprecationWarning,
                    stacklevel=4,
                )
                logger.warning(
                    f"Deprecated: 'value' parameter used for '{action_type}' action. " + f"Use '{param.name}' instead."
                )
        elif issubclass(action_cls, InteractionAction):
            # InteractionActions already use 'value' as the field name, no transformation needed
            # But if they also have id/selector from old API, handle that
            pass

    # Fast path: use registry to get the action class
    if action_type in BaseAction.ACTION_REGISTRY:
        action_cls = BaseAction.ACTION_REGISTRY[action_type]
        # Use model_validate for fast conversion
        return action_cls.model_validate(data)

    # Fallback: use ActionValidation for validation
    return ActionValidation.model_validate({"action": data}).action


def parse_action(action: "BaseAction | None" = None, **kwargs: Any) -> "BaseAction | ActionUnion":
    from notte_core.actions.actions import (
        ActionValidation,
        BaseAction,
    )

    # Fast path: if action is already a BaseAction, use it directly
    if isinstance(action, BaseAction):
        step_action = action
    elif kwargs:
        if "type" not in kwargs:
            raise ValueError("Missing required action field: 'type'")
        # Convert kwargs to BaseAction using fast mapping
        step_action = action_dict_to_base_action(kwargs)  # type: ignore[arg-type]
    elif action is None:
        raise ValueError("No action provided")
    else:
        # Fallback for dict (shouldn't happen with new API, but kept for compatibility)
        # Handle selector without id case
        if isinstance(action, dict):  # pyright: ignore[reportUnreachable]
            if "selector" in action and "id" not in action:  # pyright: ignore[reportUnreachable]
                action["id"] = ""  # pyright: ignore[reportUnreachable]
            step_action = ActionValidation.model_validate({"action": action}).action
        else:
            raise ValueError(f"Invalid action type: {type(action)}")  # pyright: ignore[reportUnreachable]

    return step_action
