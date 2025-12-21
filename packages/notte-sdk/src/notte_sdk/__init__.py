"""Notte SDK - Fast, lazy-loading SDK for web automation.

This module defers importing heavy dependencies until they are first
accessed by the user. Public API remains unchanged.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

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


def _get_version() -> str:
    """Lazily get and cache the package version."""
    global _version
    if _version is None:
        from notte_core import check_notte_version

        _version = check_notte_version("notte_sdk")
    return _version


def __getattr__(name: str) -> Any:
    """Implement lazy loading of module attributes."""
    if name == "__version__":
        return _get_version()

    if name in _lazy_imports:
        module_name, attr_name = _lazy_imports[name]
        module = import_module(module_name)
        attr = getattr(module, attr_name)
        # Cache the import for future access
        globals()[name] = attr
        return attr

    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


def __dir__() -> list[str]:
    """Return the list of public attributes."""
    return __all__
