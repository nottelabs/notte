from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Callable, Literal, TypeAlias, overload

from loguru import logger
from typing_extensions import override

from notte_core.agent_types import AgentCompletion
from notte_core.browser.observation import ExecutionResult, Observation, Screenshot

TrajectoryHoldee = ExecutionResult | Observation | AgentCompletion | Screenshot
StepId: TypeAlias = int


class TrajectoryElement:
    def __init__(self, elem: TrajectoryHoldee, step_id: StepId | None = None):
        self.inner: TrajectoryHoldee = elem
        self.step_id: StepId | None = step_id


ElementLiteral: TypeAlias = Literal["observation", "execution_result", "agent_completion", "screenshot"]


@dataclass
class StepBundle:
    agent_completion: AgentCompletion | None = None
    execution_result: ExecutionResult | None = None
    observation: Observation | None = None
    screenshot: Screenshot | None = None

    @staticmethod
    def get_element_key(element: TrajectoryHoldee) -> ElementLiteral:
        if isinstance(element, Observation):
            return "observation"
        elif isinstance(element, ExecutionResult):
            return "execution_result"
        elif isinstance(element, Screenshot):
            return "screenshot"
        elif isinstance(element, AgentCompletion):  # pyright: ignore [reportUnnecessaryIsInstance]
            return "agent_completion"
        else:
            raise ValueError("invalid element")  # pyright: ignore [reportUnreachable]


class Trajectory:
    """Shared trajectory between agent and session

    Elements are observations, agent completions and execution results
    Steps are bundles of elements, typically for use in agent loops (observe -> completion -> execute)
    The trajectory helps you iterate on all kinds of elements, either by type, or by step
    """

    def __init__(self, elements: list[TrajectoryElement] | None = None):
        if elements is None:
            elements = []

        self._step_starts: dict[StepId, int] = {}  # start steps
        self.__current_step: list[StepId | None] = [None]  # only a list because it needs to be a pointer
        self._elements: list[TrajectoryElement] = elements  # underlying elements
        self._slice: slice | None = None  # note if main, slice of the elements list if a view
        self.main_trajectory: Trajectory | None = None  # none if main, point to the main trajectory if a view
        self.callbacks: dict[
            ElementLiteral | Literal["step", "any"],
            Callable[[TrajectoryHoldee | StepBundle], None],
        ] = {}

    def stop(self) -> None:
        """Stops listing new steps in current view"""
        if self._slice is None:
            self._slice = slice(None, len(self._elements))
        else:
            self._slice = slice(self._slice.start, len(self._elements), self._slice.step)

    @property
    def num_steps(self) -> int:
        """Counts the number of committed steps"""
        return sum(1 for _ in self.step_starts) - (1 if self._current_step is not None else 0)

    @property
    def _current_step(self) -> StepId | None:
        return self.__current_step[0]

    @_current_step.setter
    def _current_step(self, value: StepId | None) -> None:
        self.__current_step[0] = value

    @property
    def step_starts(self) -> dict[StepId, int]:
        if self._slice is None:
            return self._step_starts

        current_start, current_stop, _ = self._slice.indices(len(self._elements))
        return {
            step_id: start
            for step_id, start in self._step_starts.items()
            if start >= current_start and start < current_stop
        }

    def start_step(self) -> StepId:
        if self._current_step is not None:
            raise ValueError(f"Currently in step {self._current_step}, stop it before starting a new step")

        last_step_id = max(self._step_starts.keys(), default=-1)
        next_step_id = last_step_id + 1

        self._step_starts[next_step_id] = len(self._elements)
        self._current_step = next_step_id
        return self._current_step

    def stop_step(self, ignore_not_in_step: bool = False) -> StepId | None:
        if self.main_trajectory is not None:
            return self.main_trajectory.stop_step(ignore_not_in_step=ignore_not_in_step)
        else:
            if self._current_step is None and not ignore_not_in_step:
                raise ValueError("Not currently in step, can't stop current step")
            tmp = self._current_step
            self._current_step = None

            # actually stopped a step, apply callback
            if tmp is not None and (callback := self.callbacks.get("step")) is not None:
                callback(self._get_by_step(tmp))

        return tmp

    def _get_by_step(self, step_id: StepId, raise_if_multiple: bool = False) -> StepBundle:
        if step_id not in self.step_starts:
            raise ValueError(f"Invalid step id {step_id}")

        step_start = self.step_starts[step_id]
        per_type_dict: dict[str, TrajectoryHoldee] = {}

        for elem in self._elements[step_start:]:
            if elem.step_id == step_id:
                key = StepBundle.get_element_key(elem.inner)

                if key in per_type_dict and raise_if_multiple:
                    raise ValueError(
                        f"Multiple items in trajectory match {key} for step {step_id}: '{per_type_dict[key]}'"
                    )
                else:
                    per_type_dict[key] = elem.inner

        return StepBundle(**per_type_dict)  # pyright: ignore [reportArgumentType]

    def step_iterator(self) -> Iterator[StepBundle]:
        return (self._get_by_step(step) for step in self.step_starts)

    @property
    def inner_elements(self) -> list[TrajectoryElement]:
        return self._elements[self._slice] if self._slice else self._elements

    @property
    def elements(self) -> Iterator[TrajectoryHoldee]:
        return (element.inner for element in self.inner_elements)

    def debug_log(self) -> None:
        for line in str(self).split("\n"):
            color = (
                "b"
                if "Observation" in line
                else "r"
                if "AgentCompletion" in line
                else "g"
                if "ExecutionResult" in line
                else "w"
            )
            logger.opt(colors=True).info(f"<{color}>{{line}}</{color}>", line=line)

    def __iter__(self):
        return iter(self.elements)

    def __getitem__(self, index: int) -> TrajectoryHoldee:
        return self.inner_elements[index].inner

    def __len__(self) -> int:
        return len(self.inner_elements)

    @overload
    def set_callback(
        self,
        on: Literal["any"],
        callback: Callable[[TrajectoryHoldee], None],
    ) -> None: ...

    @overload
    def set_callback(
        self,
        on: Literal["observation"],
        callback: Callable[[Observation], None],
    ) -> None: ...

    @overload
    def set_callback(
        self,
        on: Literal["execution_result"],
        callback: Callable[[ExecutionResult], None],
    ) -> None: ...

    @overload
    def set_callback(
        self,
        on: Literal["agent_completion"],
        callback: Callable[[AgentCompletion], None],
    ) -> None: ...

    @overload
    def set_callback(
        self,
        on: Literal["screenshot"],
        callback: Callable[[Screenshot], None],
    ) -> None: ...

    @overload
    def set_callback(
        self,
        on: Literal["step"],
        callback: Callable[[StepBundle], None],
    ) -> None: ...

    def set_callback(
        self,
        on: ElementLiteral | Literal["step", "any"],
        callback: Callable[..., None],
    ) -> None:
        if self.main_trajectory is not None:
            self.main_trajectory.set_callback(on, callback)
        else:
            # we're in the main trajectory, apply callbacks
            self.callbacks[on] = callback

    def append(self, element: TrajectoryHoldee, force: bool = False) -> None:
        if self._slice is not None and not force:
            raise ValueError("Cannot append to a trajectory view. Use the force to append to the original trajectory")

        if self.main_trajectory is not None:
            self.main_trajectory.append(element, force=force)
        else:
            # we're in the main trajectory, apply callbacks
            cb_key = StepBundle.get_element_key(element)
            specific_callback = self.callbacks.get(cb_key)
            any_callback = self.callbacks.get("any")
            for callback in (any_callback, specific_callback):
                if callback is not None:
                    callback(element)

                    logger.trace(f"Running {cb_key} callback")

            self._elements.append(TrajectoryElement(element, self._current_step))

    @overload
    def filter_by_type(self, element_type: type[Observation]) -> Iterator[Observation]: ...

    @overload
    def filter_by_type(self, element_type: type[Screenshot]) -> Iterator[Screenshot]: ...

    @overload
    def filter_by_type(self, element_type: type[ExecutionResult]) -> Iterator[ExecutionResult]: ...

    @overload
    def filter_by_type(self, element_type: type[AgentCompletion]) -> Iterator[AgentCompletion]: ...

    def filter_by_type(self, element_type: type[TrajectoryHoldee]) -> Iterator[TrajectoryHoldee]:
        return (step for step in self.elements if isinstance(step, element_type))

    def screenshots(self) -> Iterator[Screenshot]:
        return self.filter_by_type(Screenshot)

    def _get_next_action_id(self, elements_list: list[TrajectoryHoldee], current_index: int) -> str | None:
        """Get the action ID from the next ExecutionResult after the current index."""
        for j in range(current_index + 1, len(elements_list)):
            next_step = elements_list[j]
            if isinstance(next_step, ExecutionResult):
                if hasattr(next_step.action, "id"):
                    return getattr(next_step.action, "id")
                break
        return None

    def all_screenshots(self) -> Iterator[Screenshot]:
        # Convert elements to list to allow lookahead
        elements_list = list(self.elements)

        for i, step in enumerate(elements_list):
            if isinstance(step, Observation):
                next_action_id = self._get_next_action_id(elements_list, i)

                # Create a new screenshot with the action ID of the following ExecutionResult
                screenshot = step.screenshot
                new_screenshot = Screenshot(raw=screenshot.raw, bboxes=screenshot.bboxes, last_action_id=next_action_id)
                yield new_screenshot
            elif isinstance(step, Screenshot):
                yield step

    def observations(self) -> Iterator[Observation]:
        # Convert elements to list to allow lookahead
        elements_list = list(self.elements)

        for i, step in enumerate(elements_list):
            if isinstance(step, Observation):
                next_action_id = self._get_next_action_id(elements_list, i)

                # Create a new screenshot with the action ID of the following ExecutionResult
                screenshot = step.screenshot
                new_screenshot = Screenshot(raw=screenshot.raw, bboxes=screenshot.bboxes, last_action_id=next_action_id)
                yield step.model_copy(update={"screenshot": new_screenshot})

    def execution_results(self) -> Iterator[ExecutionResult]:
        return self.filter_by_type(ExecutionResult)

    def agent_completions(self) -> Iterator[AgentCompletion]:
        return self.filter_by_type(AgentCompletion)

    @overload
    def last_element(self, element_type: type[Screenshot]) -> Screenshot | None: ...

    @overload
    def last_element(self, element_type: type[Observation]) -> Observation | None: ...

    @overload
    def last_element(self, element_type: type[ExecutionResult]) -> ExecutionResult | None: ...

    @overload
    def last_element(self, element_type: type[AgentCompletion]) -> AgentCompletion | None: ...

    def last_element(self, element_type: type[TrajectoryHoldee]) -> TrajectoryHoldee | None:
        for step in reversed(self.inner_elements):
            if isinstance(step.inner, element_type):
                return step.inner
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

    @property
    def last_completion(self) -> AgentCompletion | None:
        return self.last_element(AgentCompletion)

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
            new_start, new_stop, _ = new_slice.indices(len(self.inner_elements))

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
        traj._step_starts = self._step_starts
        traj.__current_step = self.__current_step
        return traj

    @override
    def __repr__(self) -> str:
        """Return a concise representation showing step count and element counts."""
        num_observations = len(list(self.observations()))
        num_executions = len(list(self.execution_results()))
        num_completions = len(list(self.agent_completions()))

        return f"Trajectory(steps={self.num_steps}, observations={num_observations}, executions={num_executions}, completions={num_completions})"

    @override
    def __str__(self) -> str:
        """Return a detailed string representation listing all elements briefly."""
        lines = [f"Trajectory with {len(self)} elements:"]

        for inner_element in self.inner_elements:
            element = inner_element.inner
            step_id_str = f", step={inner_element.step_id}" if inner_element.step_id is not None else ""

            match element:
                case Observation():
                    url = element.metadata.url if hasattr(element.metadata, "url") else "unknown"
                    lines.append(f" Observation({url}{step_id_str})")
                case ExecutionResult():
                    action_name = type(element.action).__name__ if element.action else "None"
                    success = element.success
                    lines.append(f" ExecutionResult({action_name}, success={success}{step_id_str})")
                case Screenshot():
                    lines.append(" Screenshot()")
                case AgentCompletion():
                    lines.append(f" AgentCompletion(next_goal={element.state.next_goal}{step_id_str})")

        return "\n".join(lines)
