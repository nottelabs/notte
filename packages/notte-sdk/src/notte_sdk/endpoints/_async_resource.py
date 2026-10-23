import asyncio
from abc import ABC, abstractmethod
from collections.abc import Generator
from types import TracebackType
from typing import Any, Self


class AwaitableResource(ABC):
    """`notte_core.resource.SyncResource` for the `AsyncNotteClient` objects, with the same method names.

    The sync objects call the API in their constructor, which an async constructor cannot do:
    `await obj` (or `async with obj`) runs `start()` instead and returns the object.
    `start()` only calls the API the first time.
    """

    async def start(self) -> None:
        """Create or fetch the resource, once: concurrent callers wait for the first one."""
        # Without the lock, two tasks could both see an unstarted object and each create one,
        # leaving the first untracked and never deleted. Created on first use, so it binds to that loop.
        lock = self.__dict__.setdefault("_start_lock", asyncio.Lock())
        async with lock:
            await self._start()

    @abstractmethod
    async def _start(self) -> None:
        """Create or fetch the resource unless that was already done."""

    @abstractmethod
    async def stop(self) -> None: ...

    async def reset(self) -> None:
        """
        Resets the resource to its initial state. Equivalent to calling `stop` and `start` in sequence.
        """
        await self.stop()
        await self.start()

    async def _started(self) -> Self:
        await self.start()
        return self

    def __await__(self) -> Generator[Any, None, Self]:
        return self._started().__await__()

    async def __aenter__(self) -> Self:
        return await self._started()

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: TracebackType | None
    ) -> None:
        await self.stop()
