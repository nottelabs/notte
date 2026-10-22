from notte_core import check_notte_version

from notte_sdk.actions import (
    CaptchaSolve,
    Check,
    Click,
    CloseTab,
    DownloadFile,
    FallbackFill,
    Fill,
    FormFill,
    GoBack,
    GoForward,
    Goto,
    GotoNewTab,
    MultiFactorFill,
    PressKey,
    Reload,
    ScrollDown,
    ScrollUp,
    SelectDropdownOption,
    SwitchTab,
    UploadFile,
    Wait,
)
from notte_sdk.client import AsyncNotteClient, NotteClient
from notte_sdk.endpoints.sessions import RemoteSession
from notte_sdk.errors import retry
from notte_sdk.utils import generate_cookies

__version__ = check_notte_version("notte_sdk")

__all__ = [
    "NotteClient",
    "AsyncNotteClient",
    "RemoteSession",
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
    "Click",
    "Fill",
    "MultiFactorFill",
    "FallbackFill",
    "Check",
    "SelectDropdownOption",
    "UploadFile",
    "DownloadFile",
]


from notte_sdk import _v1_aliases as _v1_aliases  # noqa: E402
