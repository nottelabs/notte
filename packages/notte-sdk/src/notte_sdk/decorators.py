from __future__ import annotations

import functools
from typing import TYPE_CHECKING, Any, Callable, ParamSpec, TypeVar

if TYPE_CHECKING:
    pass

P = ParamSpec("P")
R = TypeVar("R")


def workflow(name: str, description: str | None = None) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """
    Decorator to mark a function as a Notte workflow.

    This decorator stores metadata on the function that can be used by the CLI
    to manage the workflow lifecycle (create, update, run).

    Args:
        name: The name of the workflow.
        description: Optional description of the workflow.

    Example:
        ```python
        from notte_sdk import workflow

        @workflow(name="My Workflow", description="Does something useful")
        def run(url: str, query: str) -> str:
            # workflow code here
            return "result"
        ```
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        # Store metadata on the function
        func.__workflow_name__ = name  # type: ignore[attr-defined]
        func.__workflow_description__ = description  # type: ignore[attr-defined]
        func.__is_workflow__ = True  # type: ignore[attr-defined]

        # Preserve function signature and behavior
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            return func(*args, **kwargs)

        # Handle async functions
        import inspect

        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
                return await func(*args, **kwargs)

            # Copy metadata to async wrapper
            async_wrapper.__workflow_name__ = name  # type: ignore[attr-defined]
            async_wrapper.__workflow_description__ = description  # type: ignore[attr-defined]
            async_wrapper.__is_workflow__ = True  # type: ignore[attr-defined]
            return async_wrapper  # type: ignore[return-value]

        return wrapper

    return decorator


def is_workflow(func: Callable[..., Any]) -> bool:
    """
    Check if a function is decorated with @workflow.

    Args:
        func: The function to check.

    Returns:
        True if the function is a workflow, False otherwise.
    """
    return hasattr(func, "__is_workflow__") and getattr(func, "__is_workflow__", False)


def get_workflow_name(func: Callable[..., Any]) -> str | None:
    """
    Get the workflow name from a decorated function.

    Args:
        func: The workflow function.

    Returns:
        The workflow name, or None if not found.
    """
    return getattr(func, "__workflow_name__", None)


def get_workflow_description(func: Callable[..., Any]) -> str | None:
    """
    Get the workflow description from a decorated function.

    Args:
        func: The workflow function.

    Returns:
        The workflow description, or None if not found.
    """
    return getattr(func, "__workflow_description__", None)
