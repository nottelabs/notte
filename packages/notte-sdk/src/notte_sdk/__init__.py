from notte_core import check_notte_version

from notte_sdk.actions import (
    CaptchaSolve,
    Check,
    Click,
    CloseTab,
    Completion,
    DownloadFile,
    EmailRead,
    FallbackFill,
    Fill,
    FormFill,
    GoBack,
    GoForward,
    Goto,
    GotoNewTab,
    Help,
    MultiFactorFill,
    PressKey,
    Reload,
    Scrape,
    ScrollDown,
    ScrollUp,
    SelectDropdownOption,
    SmsRead,
    SwitchTab,
    UploadFile,
    Wait,
)
from notte_sdk.client import NotteClient
from notte_sdk.endpoints.agents import RemoteAgent
from notte_sdk.endpoints.sessions import RemoteSession
from notte_sdk.errors import retry
from notte_sdk.utils import generate_cookies

__version__ = check_notte_version("notte_sdk")

__all__ = [
    "NotteClient",
    "RemoteSession",
    "RemoteAgent",
    "retry",
    "generate_cookies",
    "FormFill",
    "Goto",
    "GotoNewTab",
    "CloseTab",
    "SwitchTab",
    "GoBack",
    "GoForward",
    "Reload",
    "Wait",
    "PressKey",
    "ScrollUp",
    "ScrollDown",
    "CaptchaSolve",
    "Help",
    "Completion",
    "Scrape",
    "EmailRead",
    "SmsRead",
    "Click",
    "Fill",
    "MultiFactorFill",
    "FallbackFill",
    "Check",
    "SelectDropdownOption",
    "UploadFile",
    "DownloadFile",
]
