from abc import ABC, abstractmethod
from types import TracebackType
from typing import Any, Self

from typing_extensions import override


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
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self.astop()


class SyncResource(ABC):
    @abstractmethod
    def start(self) -> None: ...

    @abstractmethod
    def stop(self) -> None: ...

    def reset(self) -> None:
        """
        Resets the resource to its initial state. Equivalent to calling `stop` and `start` in sequence.
        """
        self.stop()
        self.start()

    def __enter__(self) -> Self:
        self.start()
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: TracebackType | None
    ) -> None:
        self.stop()


class Singleton(type):
    _instances: dict[type, Any] = {}

    @override
    def __call__(cls, *args: Any, **kwargs: Any) -> Any:
        if cls not in cls._instances:  # pyright: ignore[reportUnnecessaryContains]
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]
