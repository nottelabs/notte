from abc import ABC, abstractmethod
from typing import Protocol, Self, runtime_checkable

from typing_extensions import override


@runtime_checkable
class AsyncResourceProtocol(Protocol):
    async def start(self) -> None: ...
    async def stop(self) -> None: ...


class AsyncResource(ABC):
    @abstractmethod
    async def astart(self) -> None: ...

    @abstractmethod
    async def astop(self) -> None: ...

    async def areset(self) -> None:
        await self.astop()
        await self.astart()

    async def __aenter__(self) -> Self:
        await self.astart()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException],
        exc_val: BaseException,
        exc_tb: type[BaseException] | None,
    ) -> None:
        await self.astop()


class SyncResource(ABC):
    @abstractmethod
    def start(self) -> None: ...

    @abstractmethod
    def stop(self) -> None: ...

    def reset(self) -> None:
        self.stop()
        self.start()

    def __enter__(self) -> Self:
        self.start()
        return self

    def __exit__(
        self, exc_type: type[BaseException], exc_val: BaseException, exc_tb: type[BaseException] | None
    ) -> None:
        self.stop()


class AsyncResourceWrapper(AsyncResource):
    def __init__(self, resource: AsyncResourceProtocol) -> None:
        self._resource: AsyncResourceProtocol = resource
        self._started: bool = False

    @override
    async def astart(self) -> None:
        await self._resource.start()
        self._started = True

    @override
    async def astop(self) -> None:
        if not self._started:
            raise ValueError(f"{self._resource.__class__.__name__} not started")
        await self._resource.stop()
