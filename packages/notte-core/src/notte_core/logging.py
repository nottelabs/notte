from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any, TypeVar

import loguru
from loguru import logger as _loguru_logger


class _LoggerProxy:
    def __getattr__(self, name: str):
        current_logger = get_logger()
        return getattr(current_logger, name)


def get_logger() -> loguru.Logger:
    return _loguru_logger.bind(package="notte")


logger: loguru.Logger = _LoggerProxy()  # pyright: ignore [reportAssignmentType]

F = TypeVar("F", bound=Callable[..., Any])


def timeit(name: str) -> Callable[[F], F]:
    def _timeit(func: F) -> F:
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            start_time = time.time()
            result = await func(*args, **kwargs)
            end_time = time.time()
            logger.debug(f"function {name} took {end_time - start_time:.4f} seconds")
            return result

        return wrapper  # type: ignore

    return _timeit
