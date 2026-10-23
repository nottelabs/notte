"""The multi-request operations of the stateful layer, written once for the sync and async clients.

A flow is a generator holding every decision of an operation (polling, retries, deadlines). It
yields the I/O it needs, a `Call` of a client method or a `Sleep`, and receives each call's
result, or has the call's exception thrown in. `run` performs those steps with blocking calls and
`time.sleep`; `arun` awaits them and `asyncio.sleep`. `NotteClient` and `AsyncNotteClient`
resources have the same method names, so one flow serves both.
"""

import asyncio
import time
from collections.abc import Generator, Mapping
from dataclasses import dataclass, field
from typing import Any, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class Call:
    """Call the client method `method`; the flow receives its result or exception."""

    method: str
    args: tuple[Any, ...] = ()
    kwargs: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Sleep:
    seconds: float


Flow = Generator[Call | Sleep, Any, T]


def run(client: Any, flow: Flow[T]) -> T:
    """Run `flow` with blocking calls of `client`'s methods."""
    result: Any = None
    error: Exception | None = None
    while True:
        try:
            step = flow.send(result) if error is None else flow.throw(error)
        except StopIteration as stop:
            return stop.value
        result, error = None, None
        if isinstance(step, Sleep):
            time.sleep(step.seconds)
            continue
        try:
            result = getattr(client, step.method)(*step.args, **step.kwargs)
        except Exception as exc:
            error = exc


async def arun(client: Any, flow: Flow[T], *, in_thread: bool = False) -> T:
    """Run `flow` awaiting `client`'s coroutine methods, or its blocking methods in a thread with `in_thread`."""
    result: Any = None
    error: Exception | None = None
    while True:
        try:
            step = flow.send(result) if error is None else flow.throw(error)
        except StopIteration as stop:
            return stop.value
        result, error = None, None
        if isinstance(step, Sleep):
            await asyncio.sleep(step.seconds)
            continue
        method = getattr(client, step.method)
        try:
            if in_thread:
                result = await asyncio.to_thread(method, *step.args, **step.kwargs)
            else:
                result = await method(*step.args, **step.kwargs)
        except Exception as exc:
            error = exc
