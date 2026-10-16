"""Runtime-only aliases for notte 1.9 SDK names. Delete this file and its activation import in 2.0."""

import warnings
from collections.abc import Callable
from functools import wraps
from typing import Any

from notte_sdk.client import NotteClient
from notte_sdk.endpoints.functions import FunctionsClient, NotteFunction
from notte_sdk.endpoints.personas import PersonasClient
from notte_sdk.endpoints.sessions import SessionsClient
from notte_sdk.endpoints.vaults import VaultsClient

_RENAMED_METHODS: dict[type, dict[str, str]] = {
    VaultsClient: {
        "get_credentials": "credentials_get",
        "list_credentials": "credentials_list",
        "add_or_update_credentials": "credentials_add",
        "delete_credentials": "credentials_delete",
        "get_credit_card": "credit_card_get",
        "set_credit_card": "credit_card_set",
        "delete_credit_card": "credit_card_delete",
    },
    PersonasClient: {"list_emails": "emails_list", "list_sms": "sms_list"},
    FunctionsClient: {
        "get": "download_url",
        "get_run": "run_get_metadata",
        "run": "run_start",
        "stop_run": "run_stop",
        "update_run": "run_update_metadata",
    },
    SessionsClient: {"auth_status": "auth_readiness"},
}
_RENAMED_ATTRS: dict[type, dict[str, str]] = {
    NotteClient: {"workflows": "functions", "Workflow": "Function"},
    NotteFunction: {"workflow_id": "function_id"},
}
_RENAMED_KWARGS = {"Workflow": {"workflow_id": "function_id", "workflow_path": "path"}}
_DROPPED_KWARGS: dict[Callable[..., Any], dict[str, Any]] = {NotteFunction.run: {"local": False}}
_warned: set[str] = set()


def _warn(old: str, new: str) -> None:
    if old not in _warned:
        _warned.add(old)
        warnings.warn(
            f"`{old}` is deprecated and will be removed in notte 2.0; use `{new}` instead.",
            DeprecationWarning,
            stacklevel=3,
        )


def _method(cls: type, old: str, new: str) -> Callable[..., Any]:
    @wraps(getattr(cls, new))
    def alias(self: Any, *args: Any, **kwargs: Any) -> Any:
        _warn(f"{cls.__name__}.{old}", f"{cls.__name__}.{new}")
        return getattr(self, new)(*args, **kwargs)

    return alias


def _attribute(cls: type, old: str, new: str) -> property:
    def alias(self: Any) -> Any:
        _warn(f"{cls.__name__}.{old}", f"{cls.__name__}.{new}")
        value = getattr(self, new)
        if old not in _RENAMED_KWARGS:
            return value

        @wraps(value)
        def factory(*args: Any, **kwargs: Any) -> Any:
            for before, after in _RENAMED_KWARGS[old].items():
                if before in kwargs:
                    previous = kwargs.pop(before)
                    if previous is None:
                        continue
                    if after in kwargs and kwargs[after] != previous:
                        raise ValueError(f"Cannot specify both {before!r} and {after!r} with different values")
                    kwargs[after] = previous
            return value(*args, **kwargs)

        return factory

    return property(alias)


def _drop_kwargs(method: Callable[..., Any], dropped: dict[str, Any]) -> Callable[..., Any]:
    @wraps(method)
    def alias(*args: Any, **kwargs: Any) -> Any:
        for name, default in dropped.items():
            if name in kwargs:
                value = kwargs.pop(name)
                if value is not default:
                    raise ValueError(
                        f"{method.__qualname__}({name}={value!r}): local execution was removed in notte 1.10; "
                        + f"use {method.__qualname__}() for cloud execution."
                    )
                _warn(f"{method.__qualname__}({name}=False)", f"{method.__qualname__}() without `{name}`")
        return method(*args, **kwargs)

    return alias


def install() -> None:
    for cls, aliases in _RENAMED_METHODS.items():
        for old, new in aliases.items():
            setattr(cls, old, _method(cls, old, new))
    for cls, aliases in _RENAMED_ATTRS.items():
        for old, new in aliases.items():
            setattr(cls, old, _attribute(cls, old, new))
    for method, dropped in _DROPPED_KWARGS.items():
        # Only NotteFunction.run has a removed keyword with an exact remote equivalent.
        setattr(NotteFunction, method.__name__, _drop_kwargs(method, dropped))


install()
