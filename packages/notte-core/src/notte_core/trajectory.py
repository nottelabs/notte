from __future__ import annotations

from collections.abc import Awaitable, Iterator
from typing import Callable, Literal, TypeAlias, overload

from typing_extensions import override

from notte_core.browser.observation import ExecutionResult, Observation, Screenshot
from notte_core.common.logging import logger
from notte_core.profiling import profiler

TrajectoryHoldee = ExecutionResult | Observation | Screenshot

ElementLiteral: TypeAlias = Literal["observation", "execution_result", "screenshot"]


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
    """Ordered record of a session's observations, execution results and screenshots.

    Views (see `view`) share the underlying elements and callbacks but only expose
    what was appended after they were created.
    """

    def __init__(self, elements: list[TrajectoryHoldee] | None = None):
        self._elements: list[TrajectoryHoldee] = elements if elements is not None else []
        self._slice: slice | None = None  # note if main, slice of the elements list if a view
        self.main_trajectory: Trajectory | None = None  # none if main, point to the main trajectory if a view
        self.callbacks: dict[
            ElementLiteral | Literal["any"],
            Callable[[TrajectoryHoldee], Awaitable[None]],
        ] = {}

    def stop(self) -> None:
        """Stops listing new elements in current view"""

        if self._slice is None:
            self._slice = slice(None, len(self._elements))
        else:
            self._slice = slice(self._slice.start, len(self._elements), self._slice.step)

    @property
    def elements(self) -> list[TrajectoryHoldee]:
        return self._elements[self._slice] if self._slice else self._elements

    def debug_log(self) -> None:
        obtained_str = str(self)
        for line in obtained_str.split("\n"):
            color = "b" if "Observation" in line else "g" if "ExecutionResult" in line else "w"
            logger.opt(colors=True).info(f"<{color}>{{line}}</{color}>", line=line)

    def __iter__(self) -> Iterator[TrajectoryHoldee]:
        return iter(self.elements)

    def __getitem__(self, index: int) -> TrajectoryHoldee:
        return self.elements[index]

    def __len__(self) -> int:
        return len(self.elements)

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
        if self.main_trajectory is not None:
            self.main_trajectory.set_callback(on, callback)
        else:
            # we're in the main trajectory, apply callbacks
            self.callbacks[on] = callback

    async def append(self, element: TrajectoryHoldee, force: bool = False) -> None:
        if self._slice is not None and not force:
            raise ValueError("Cannot append to a trajectory view. Use the force to append to the original trajectory")

        if self.main_trajectory is not None:
            await self.main_trajectory.append(element, force=force)
        else:
            # we're in the main trajectory, apply callbacks
            cb_key = get_element_key(element)
            specific_callback = self.callbacks.get(cb_key)
            any_callback = self.callbacks.get("any")
            for callback in (any_callback, specific_callback):
                if callback is not None:
                    async with profiler.profile(f"Callback {cb_key}"):
                        logger.trace(f"Running {cb_key} callback")
                        await callback(element)

            self._elements.append(element)

    @overload
    def filter_by_type(self, element_type: type[Observation]) -> Iterator[Observation]: ...

    @overload
    def filter_by_type(self, element_type: type[Screenshot]) -> Iterator[Screenshot]: ...

    @overload
    def filter_by_type(self, element_type: type[ExecutionResult]) -> Iterator[ExecutionResult]: ...

    def filter_by_type(self, element_type: type[TrajectoryHoldee]) -> Iterator[TrajectoryHoldee]:
        return (step for step in self.elements if isinstance(step, element_type))

    def screenshots(self) -> Iterator[Screenshot]:
        return self.filter_by_type(Screenshot)

    def observations(self) -> Iterator[Observation]:
        return self.filter_by_type(Observation)

    def execution_results(self) -> Iterator[ExecutionResult]:
        return self.filter_by_type(ExecutionResult)

    @overload
    def last_element(self, element_type: type[Screenshot]) -> Screenshot | None: ...

    @overload
    def last_element(self, element_type: type[Observation]) -> Observation | None: ...

    @overload
    def last_element(self, element_type: type[ExecutionResult]) -> ExecutionResult | None: ...

    def last_element(self, element_type: type[TrajectoryHoldee]) -> TrajectoryHoldee | None:
        for step in reversed(self.elements):
            if isinstance(step, element_type):
                return step
        return None

    @property
    def last_screenshot(self) -> Screenshot | None:
        return self.last_element(Screenshot)

    @property
    def last_observation(self) -> Observation | None:
        return self.last_element(Observation)

    @property
    def last_result(self) -> ExecutionResult | None:
        return self.last_element(ExecutionResult)

    def view(self) -> "Trajectory":
        """Create a view at the current time in the trajectory"""
        return self._view(start=len(self._elements))

    def _view(self, start: int | None = None, stop: int | None = None) -> "Trajectory":
        """Create a view on a slice of this trajectory.

        stop is deprecated, should not be set unless you know what you're doing
        """
        # If this is already a view, we need to compose the slices
        if self._slice is not None:
            # Get the current slice indices
            current_start, _, _ = self._slice.indices(len(self._elements))
            # Calculate the new slice relative to the current view
            new_slice = slice(start, stop, 1)
            new_start, new_stop, _ = new_slice.indices(len(self.elements))

            # Convert to absolute indices in the original list
            abs_start = current_start + new_start
            if stop is not None:
                abs_stop = current_start + new_stop
            else:
                abs_stop = None

            traj = Trajectory(self._elements)
            traj_slice = slice(abs_start, abs_stop, 1)

        else:
            # This is not a view, so just apply the slice directly
            traj = Trajectory(self._elements)
            traj_slice = slice(start, stop, 1)

        # keep a pointer to the root for appending
        if self.main_trajectory is not None:
            traj.main_trajectory = self.main_trajectory
        else:
            traj.main_trajectory = self

        traj.callbacks = self.callbacks
        traj._slice = traj_slice
        return traj

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

        for element in self.elements:
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
