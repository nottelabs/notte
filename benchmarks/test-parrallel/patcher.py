from __future__ import annotations

import asyncio
import functools
import json
import time
from collections import defaultdict
from typing import Any, Callable

from bench_types import FunctionLog  # pyright: ignore[reportImplicitRelativeImport]
from notte_core.llms.logging import recover_args
from pydantic import BaseModel


class CantPatchFunctionError(Exception):
    pass


class CantDumpArgumentError(Exception):
    pass


class AgentPatcher:
    """Patched methods of an agent to monitor its behavior

    Only meant to be used on a singe class at a time.
    """

    def __init__(self):
        self.logged_data: dict[str, list[FunctionLog]] = defaultdict(list)
        self.prepatch_methods: dict[str, Callable[..., Any]] = {}

    @staticmethod
    def _dump_args(to_dump: Any) -> Any:
        def dump_default(value: Any) -> dict[str, Any] | str:
            if isinstance(value, BaseModel):
                ret = value.model_dump()
                return ret

            return str(value)

        return json.dumps(to_dump, default=dump_default)

    def _patch_function(
        self,
        class_with_methods: object,
        func_name: str,
        patching_function: Callable[..., Callable[..., Any]],
    ) -> None:
        func: Callable[..., Any] = getattr(class_with_methods, func_name)

        if func.__qualname__ in self.prepatch_methods:
            raise CantPatchFunctionError(f"Function {func.__qualname__} already patched")

        if func_name == "__call__":
            # Create patched version of the original unbound method
            original_unbound = class_with_methods.__class__.__call__
            patched = patching_function(original_unbound)

            # Create new class with patched __call__
            class _(type(class_with_methods)):
                def __call__(self_cls, *args, **kwargs):  # type: ignore
                    # Don't pass self_cls twice - patched already handles that
                    return patched(self_cls, *args, **kwargs)

            class_with_methods.__class__ = _
        else:
            patched = patching_function(func)
            try:
                setattr(class_with_methods, func_name, patched)
            except ValueError:
                try:
                    import pydantic

                    if isinstance(class_with_methods, pydantic.BaseModel):
                        class_with_methods.__dict__[func_name] = patched
                except ImportError:
                    raise CantPatchFunctionError(f"Could not setattr {func_name}")
            except Exception as e:
                raise CantPatchFunctionError(f"Could not setattr {func_name}: {e}")

        self.prepatch_methods[func.__qualname__] = patched

    def log(
        self,
        class_with_methods: object,
        timing_methods: list[str],
        pre_callback: Callable[..., None] | None = None,
        post_callback: Callable[..., None] | None = None,
    ) -> None:
        """Save running time of functions"""

        def logging_decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            @functools.wraps(func)
            def wrapper(*args, **kwargs):  # type: ignore
                start = time.time()

                params = recover_args(func, args, kwargs)  # type: ignore

                input_params = AgentPatcher._dump_args(params)

                if pre_callback is not None:
                    pre_callback(params)

                # If the function is async, await it
                if asyncio.iscoroutinefunction(func):

                    async def async_wrapper():
                        result = await func(*args, **kwargs)
                        end = time.time()
                        out_params = AgentPatcher._dump_args(result)
                        self.logged_data[func.__qualname__].append(
                            FunctionLog(start_time=start, end_time=end, input_data=input_params, output_data=out_params)
                        )

                        if post_callback is not None:
                            post_callback(input_params, out_params)

                        return result

                    return async_wrapper()  # Return the coroutine

                # Otherwise, run it normally
                result = func(*args, **kwargs)
                end = time.time()
                out_params = AgentPatcher._dump_args(result)
                self.logged_data[func.__qualname__].append(
                    FunctionLog(start_time=start, end_time=end, input_data=input_params, output_data=out_params)
                )

                if post_callback is not None:
                    post_callback(input_params, out_params)

                return result

            return wrapper  # type: ignore

        for func_name in timing_methods:
            self._patch_function(
                class_with_methods,
                func_name,
                logging_decorator,
            )

    def find_encompassed_events(self, container_key: str) -> list[tuple[FunctionLog, dict[str, list[FunctionLog]]]]:
        """
        For each event in container_key, find all other events that are encompassed within its time window.

        Args:
            logged_data (dict): Dictionary of logged events
            container_key (str): Key to use as the container events (default: "Agent.step")

        Returns:
            list: List of tuples (container_event, {key: list of encompassed events})
        """
        results: list[tuple[FunctionLog, dict[str, list[FunctionLog]]]] = []

        # For each container event (e.g., each Agent.step)
        for container_event in self.logged_data[container_key]:
            encompassed: dict[str, list[FunctionLog]] = {}

            # Check all other keys
            for key in self.logged_data:
                if key != container_key:  # Skip the container key itself
                    # Find all events within this key that are encompassed by the container event
                    contained_events = [
                        event
                        for event in self.logged_data[key]
                        if container_event.start_time <= event.start_time and event.end_time <= container_event.end_time
                    ]
                    if contained_events:
                        encompassed[key] = contained_events

            results.append((container_event, encompassed))

        return results
