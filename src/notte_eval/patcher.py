from __future__ import annotations

import asyncio
import functools
import json
import time
from collections import defaultdict
from enum import Enum
from functools import wraps
from typing import Any, Callable, Protocol

from pydantic import BaseModel

from notte.llms.logging import recover_args


class HasAccessors(Protocol):
    def __getattr__(self, name: str) -> Callable[..., Any]: ...


class CantPatchFunctionError(Exception):
    pass


class CantDumpArgumentError(Exception):
    pass


class AgentPatcher:
    """Patched methods of an agent to monitor its behavior

    Only meant to be used on a singe class at a time.
    """

    class PatchType(str, Enum):
        IO = "io"
        TIMING = "timing"

    def __init__(self):
        self.timing_data: dict[str, list[float]] = defaultdict(list)
        self.input_data: dict[str, list[Any]] = defaultdict(list)
        self.output_data: dict[str, list[Any]] = defaultdict(list)

        self.prepatch_methods: dict[AgentPatcher.PatchType, dict[str, Callable[..., Any]]] = defaultdict(dict)

    @staticmethod
    def _dump_args(to_dump: Any) -> Any:
        if isinstance(to_dump, BaseModel):
            return to_dump.model_dump_json()
        try:
            return json.dumps(to_dump)
        except TypeError as te:
            try:
                from langchain_core.load.dump import dumps  # type: ignore[import]

                return dumps(to_dump)  # type: ignore[import, has-type]
            except ImportError:
                raise CantDumpArgumentError from te

        except Exception as e:
            raise CantDumpArgumentError from e

    def _patch_function(
        self,
        class_with_methods: HasAccessors,
        func_name: str,
        patch_type: PatchType,
        patching_function: Callable[..., Callable[..., Any]],
    ) -> None:
        func: Callable[..., Any] = getattr(class_with_methods, func_name)
        if func.__qualname__ in self.prepatch_methods[patch_type]:
            raise CantPatchFunctionError(f"Function {func.__qualname__} already patched")

        patched = patching_function(func)
        self.prepatch_methods[patch_type][func.__qualname__] = patched

        # try to patch it simply, if it fails, check if BaseModel
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

    def log_io(self, class_with_methods: HasAccessors, functions: list[str]) -> None:
        """Save input and output of functions"""

        def input_decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            @wraps(func)
            def _func_replacer(*args: Any, **kwargs: Any) -> Any:
                params = recover_args(func, args, kwargs)

                self.input_data[func.__qualname__].append(AgentPatcher._dump_args(params))

                # If the function is async, await it
                if asyncio.iscoroutinefunction(func):

                    async def async_wrapper():
                        retval = await func(*args, **kwargs)
                        self.output_data[func.__qualname__].append(AgentPatcher._dump_args(retval))
                        return retval

                    return async_wrapper()  # Return the coroutine

                # Otherwise, run it normally
                retval = func(*args, **kwargs)
                self.output_data[func.__qualname__].append(AgentPatcher._dump_args(retval))
                return retval

            return _func_replacer

        for func_name in functions:
            self._patch_function(
                class_with_methods,
                func_name,
                AgentPatcher.PatchType.IO,
                input_decorator,
            )

    def log_timings(self, class_with_methods: HasAccessors, timing_methods: list[str]) -> None:
        """Save running time of functions"""

        def timing_decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            @functools.wraps(func)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                start = time.time()
                # If the function is async, await it
                if asyncio.iscoroutinefunction(func):

                    async def async_wrapper():
                        result = await func(*args, **kwargs)
                        end = time.time()
                        self.timing_data[func.__qualname__].append(end - start)
                        return result

                    return async_wrapper()  # Return the coroutine

                # Otherwise, run it normally
                result = func(*args, **kwargs)
                end = time.time()
                self.timing_data[func.__qualname__].append(end - start)
                return result

            return wrapper

        for func_name in timing_methods:
            self._patch_function(
                class_with_methods,
                func_name,
                AgentPatcher.PatchType.TIMING,
                timing_decorator,
            )
