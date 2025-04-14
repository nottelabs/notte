import time
from collections.abc import Callable
from typing import Any, TypeVar

from loguru import logger

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
