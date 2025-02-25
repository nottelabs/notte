from typing import Protocol, Self, runtime_checkable


@runtime_checkable
class AsyncResourceProtocol(Protocol):
    async def start(self) -> None: ...
    async def close(self) -> None: ...


class AsyncResource:
    def __init__(self, resource: AsyncResourceProtocol) -> None:
        self._resource: AsyncResourceProtocol = resource
        self._started: bool = False

    async def start(self) -> None:
        await self._resource.start()
        self._started = True

    async def close(self) -> None:
        if not self._started:
            raise ValueError(f"{self._resource.__class__.__name__} not started")
        await self._resource.close()

    async def __aenter__(self) -> Self:
        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException],
        exc_val: BaseException,
        exc_tb: type[BaseException] | None,
    ) -> None:
        await self.close()
