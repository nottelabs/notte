"""Notte SDK - Fast, lazy-loading SDK for web automation.

This module defers importing heavy dependencies until they are first
accessed by the user. Public API remains unchanged.
"""

from __future__ import annotations

import threading
from importlib import import_module
from typing import TYPE_CHECKING, Any

__all__: list[str] = [
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

_lazy_imports: dict[str, tuple[str, str]] = {
    # Client and endpoints
    "NotteClient": ("notte_sdk.client", "NotteClient"),
    "RemoteSession": ("notte_sdk.endpoints.sessions", "RemoteSession"),
    "RemoteAgent": ("notte_sdk.endpoints.agents", "RemoteAgent"),
    # Utilities
    "retry": ("notte_sdk.errors", "retry"),
    "generate_cookies": ("notte_sdk.utils", "generate_cookies"),
    # Action classes
    "CaptchaSolve": ("notte_sdk.actions", "CaptchaSolve"),
    "Check": ("notte_sdk.actions", "Check"),
    "Click": ("notte_sdk.actions", "Click"),
    "CloseTab": ("notte_sdk.actions", "CloseTab"),
    "Completion": ("notte_sdk.actions", "Completion"),
    "DownloadFile": ("notte_sdk.actions", "DownloadFile"),
    "EmailRead": ("notte_sdk.actions", "EmailRead"),
    "FallbackFill": ("notte_sdk.actions", "FallbackFill"),
    "Fill": ("notte_sdk.actions", "Fill"),
    "FormFill": ("notte_sdk.actions", "FormFill"),
    "GoBack": ("notte_sdk.actions", "GoBack"),
    "GoForward": ("notte_sdk.actions", "GoForward"),
    "Goto": ("notte_sdk.actions", "Goto"),
    "GotoNewTab": ("notte_sdk.actions", "GotoNewTab"),
    "Help": ("notte_sdk.actions", "Help"),
    "MultiFactorFill": ("notte_sdk.actions", "MultiFactorFill"),
    "PressKey": ("notte_sdk.actions", "PressKey"),
    "Reload": ("notte_sdk.actions", "Reload"),
    "Scrape": ("notte_sdk.actions", "Scrape"),
    "ScrollDown": ("notte_sdk.actions", "ScrollDown"),
    "ScrollUp": ("notte_sdk.actions", "ScrollUp"),
    "SelectDropdownOption": ("notte_sdk.actions", "SelectDropdownOption"),
    "SmsRead": ("notte_sdk.actions", "SmsRead"),
    "SwitchTab": ("notte_sdk.actions", "SwitchTab"),
    "UploadFile": ("notte_sdk.actions", "UploadFile"),
    "Wait": ("notte_sdk.actions", "Wait"),
}

_version: str | None = None
_version_lock = threading.Lock()
_import_lock = threading.Lock()


def _get_version() -> str:
    """Lazily get and cache the package version."""
    global _version
    if _version is None:
        with _version_lock:
            if _version is None:
                from notte_core import check_notte_version

                _version = check_notte_version("notte_sdk")
    # _version is str here due to the double-checked lock guard
    return _version


def __getattr__(name: str) -> Any:
    """Implement lazy loading of module attributes."""
    if name == "__version__":
        return _get_version()

    if name in _lazy_imports:
        module_name, attr_name = _lazy_imports[name]
        with _import_lock:
            module = import_module(module_name)
            attr = getattr(module, attr_name)
            # Cache the import for future access
            globals()[name] = attr
            return attr

    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


def __dir__() -> list[str]:
    """Return the list of public attributes."""
    return __all__


# Provide static typing for IDEs/type checkers without affecting runtime
if TYPE_CHECKING:
    from notte_sdk.actions import (
        CaptchaSolve as CaptchaSolve,
    )
    from notte_sdk.actions import (
        Check as Check,
    )
    from notte_sdk.actions import (
        Click as Click,
    )
    from notte_sdk.actions import (
        CloseTab as CloseTab,
    )
    from notte_sdk.actions import (
        Completion as Completion,
    )
    from notte_sdk.actions import (
        DownloadFile as DownloadFile,
    )
    from notte_sdk.actions import (
        EmailRead as EmailRead,
    )
    from notte_sdk.actions import (
        FallbackFill as FallbackFill,
    )
    from notte_sdk.actions import (
        Fill as Fill,
    )
    from notte_sdk.actions import (
        FormFill as FormFill,
    )
    from notte_sdk.actions import (
        GoBack as GoBack,
    )
    from notte_sdk.actions import (
        GoForward as GoForward,
    )
    from notte_sdk.actions import (
        Goto as Goto,
    )
    from notte_sdk.actions import (
        GotoNewTab as GotoNewTab,
    )
    from notte_sdk.actions import (
        Help as Help,
    )
    from notte_sdk.actions import (
        MultiFactorFill as MultiFactorFill,
    )
    from notte_sdk.actions import (
        PressKey as PressKey,
    )
    from notte_sdk.actions import (
        Reload as Reload,
    )
    from notte_sdk.actions import (
        Scrape as Scrape,
    )
    from notte_sdk.actions import (
        ScrollDown as ScrollDown,
    )
    from notte_sdk.actions import (
        ScrollUp as ScrollUp,
    )
    from notte_sdk.actions import (
        SelectDropdownOption as SelectDropdownOption,
    )
    from notte_sdk.actions import (
        SmsRead as SmsRead,
    )
    from notte_sdk.actions import (
        SwitchTab as SwitchTab,
    )
    from notte_sdk.actions import (
        UploadFile as UploadFile,
    )
    from notte_sdk.actions import (
        Wait as Wait,
    )
    from notte_sdk.client import NotteClient as NotteClient
    from notte_sdk.endpoints.agents import RemoteAgent as RemoteAgent
    from notte_sdk.endpoints.sessions import RemoteSession as RemoteSession
    from notte_sdk.errors import retry as retry
    from notte_sdk.utils import generate_cookies as generate_cookies
