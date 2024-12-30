from collections.abc import Awaitable, Callable
from typing import Any, TypeAlias

from playwright.async_api import Page

from notte.actions.base import ExecutableAction

ActionExecutor: TypeAlias = Callable[[Page], Awaitable[bool]]


def get_executor(action: ExecutableAction) -> ActionExecutor:
    if action.code is None:
        raise ValueError("Code cannot be None")
    # Create a new namespace to avoid polluting the global namespace
    namespace: dict[str, Any] = {}
    # Add required imports to the namespace
    exec("from playwright.sync_api import Page", namespace)  # nosec: B102
    # Execute the code string to define the function
    exec(action.code, namespace)  # nosec: B102
    # Return the function from the namespace
    return namespace["execute_user_action"]
