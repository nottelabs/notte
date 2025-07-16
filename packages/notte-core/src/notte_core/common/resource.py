from abc import ABC, abstractmethod
from typing import Self


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
