from typing import TYPE_CHECKING

from notte_core import check_notte_version

from notte_sdk.client import NotteClient
from notte_sdk.endpoints.agents import RemoteAgent
from notte_sdk.endpoints.sessions import RemoteSession
from notte_sdk.errors import retry
from notte_sdk.utils import generate_cookies

__version__ = check_notte_version("notte_sdk")

# Type hints for actions (only for type checkers, not imported at runtime)
if TYPE_CHECKING:
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

__all__ = [
    "NotteClient",
    "RemoteSession",
    "RemoteAgent",
    "retry",
    "generate_cookies",
    # Action classes (lazy loaded)
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

# Lazy loading for action classes
_action_classes = {
    "CaptchaSolve",
    "Check",
    "Click",
    "CloseTab",
    "Completion",
    "DownloadFile",
    "EmailRead",
    "FallbackFill",
    "Fill",
    "FormFill",
    "GoBack",
    "GoForward",
    "Goto",
    "GotoNewTab",
    "Help",
    "MultiFactorFill",
    "PressKey",
    "Reload",
    "Scrape",
    "ScrollDown",
    "ScrollUp",
    "SelectDropdownOption",
    "SmsRead",
    "SwitchTab",
    "UploadFile",
    "Wait",
}


def __getattr__(name: str):
    """Lazy load action classes on first access.

    This significantly improves import time by deferring the import of
    26+ action classes and their Pydantic schemas until they're actually used.
    """
    if name in _action_classes:
        # Import from actions module only when requested
        from notte_sdk import actions

        action = getattr(actions, name)
        # Cache it in the module's globals for subsequent access
        globals()[name] = action
        return action

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
