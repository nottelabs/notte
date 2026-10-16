from __future__ import annotations

from collections.abc import Awaitable, Iterator
from typing import Callable, Literal, TypeAlias, TypeVar, overload

from typing_extensions import override

from notte_core.logging import logger
from notte_core.observation import ExecutionResult, Observation, Screenshot
from notte_core.profiling import profiler

TrajectoryHoldee = ExecutionResult | Observation | Screenshot

ElementLiteral: TypeAlias = Literal["observation", "execution_result", "screenshot"]

_Holdee = TypeVar("_Holdee", ExecutionResult, Observation, Screenshot)


def get_element_key(element: TrajectoryHoldee) -> ElementLiteral:
    if isinstance(element, Observation):
        return "observation"
    elif isinstance(element, ExecutionResult):
        return "execution_result"
    elif isinstance(element, Screenshot):  # pyright: ignore [reportUnnecessaryIsInstance]
        return "screenshot"
    else:
        raise ValueError("invalid element")  # pyright: ignore [reportUnreachable]


class Trajectory:
    """Ordered record of a session's observations, execution results and screenshots."""

    def __init__(self, elements: list[TrajectoryHoldee] | None = None):
        self._elements: list[TrajectoryHoldee] = elements if elements is not None else []
        self.callbacks: dict[
            ElementLiteral | Literal["any"],
            Callable[[TrajectoryHoldee], Awaitable[None]],
        ] = {}

    @property
    def elements(self) -> list[TrajectoryHoldee]:
        return self._elements

    def __iter__(self) -> Iterator[TrajectoryHoldee]:
        return iter(self._elements)

    def __getitem__(self, index: int) -> TrajectoryHoldee:
        return self._elements[index]

    def __len__(self) -> int:
        return len(self._elements)

    @overload
    def set_callback(
        self,
        on: Literal["any"],
        callback: Callable[[TrajectoryHoldee], Awaitable[None]],
    ) -> None: ...

    @overload
    def set_callback(
        self,
        on: Literal["observation"],
        callback: Callable[[Observation], Awaitable[None]],
    ) -> None: ...

    @overload
    def set_callback(
        self,
        on: Literal["execution_result"],
        callback: Callable[[ExecutionResult], Awaitable[None]],
    ) -> None: ...

    @overload
    def set_callback(
        self,
        on: Literal["screenshot"],
        callback: Callable[[Screenshot], Awaitable[None]],
    ) -> None: ...

    def set_callback(
        self,
        on: ElementLiteral | Literal["any"],
        callback: Callable[..., Awaitable[None]],
    ) -> None:
        self.callbacks[on] = callback

    async def append(self, element: TrajectoryHoldee) -> None:
        """Run the `any` callback, then the element's own callback, then record the element."""
        cb_key = get_element_key(element)
        for callback in (self.callbacks.get("any"), self.callbacks.get(cb_key)):
            if callback is not None:
                async with profiler.profile(f"Callback {cb_key}"):
                    logger.trace(f"Running {cb_key} callback")
                    await callback(element)
        self._elements.append(element)

    def _of_type(self, element_type: type[_Holdee]) -> Iterator[_Holdee]:
        return (element for element in self._elements if isinstance(element, element_type))

    def _last_of_type(self, element_type: type[_Holdee]) -> _Holdee | None:
        return next((element for element in reversed(self._elements) if isinstance(element, element_type)), None)

    def screenshots(self) -> Iterator[Screenshot]:
        return self._of_type(Screenshot)

    def observations(self) -> Iterator[Observation]:
        return self._of_type(Observation)

    def execution_results(self) -> Iterator[ExecutionResult]:
        return self._of_type(ExecutionResult)

    @property
    def last_screenshot(self) -> Screenshot | None:
        return self._last_of_type(Screenshot)

    @property
    def last_observation(self) -> Observation | None:
        return self._last_of_type(Observation)

    @property
    def last_result(self) -> ExecutionResult | None:
        return self._last_of_type(ExecutionResult)

    @override
    def __repr__(self) -> str:
        """Return a concise representation showing element counts."""
        num_observations = len(list(self.observations()))
        num_executions = len(list(self.execution_results()))

        return f"Trajectory(observations={num_observations}, executions={num_executions})"

    @override
    def __str__(self) -> str:
        """Return a detailed string representation listing all elements briefly."""
        lines = [f"Trajectory with {len(self)} elements:"]

        for element in self._elements:
            match element:
                case Observation():
                    url = element.metadata.url if hasattr(element.metadata, "url") else "unknown"
                    lines.append(f" Observation({url})")
                case ExecutionResult():
                    action_name = type(element.action).__name__ if element.action else "None"
                    lines.append(f" ExecutionResult({action_name}, success={element.success})")
                case Screenshot():
                    lines.append(" Screenshot()")

        return "\n".join(lines)
