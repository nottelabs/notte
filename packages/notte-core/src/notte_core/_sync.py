"""Run synchronous facades on one persistent, unpatched asyncio loop per process."""

from __future__ import annotations

import asyncio
import atexit
import os
import threading
from collections.abc import Coroutine
from typing import TypeVar

T = TypeVar("T")


class _LoopThread:
    def __init__(self) -> None:
        ready = threading.Event()
        self.loop: asyncio.AbstractEventLoop = asyncio.new_event_loop()
        self.thread: threading.Thread = threading.Thread(
            target=self._run, args=(ready,), name="notte-sync", daemon=True
        )
        self.thread.start()
        _ = ready.wait()

    def _run(self, ready: threading.Event) -> None:
        # Runner closes async generators, the executor and pending tasks on shutdown.
        with asyncio.Runner(loop_factory=lambda: self.loop):
            asyncio.set_event_loop(self.loop)
            _ = self.loop.call_soon(ready.set)
            self.loop.run_forever()

    def close(self) -> None:
        _ = self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join()


_runner: _LoopThread | None = None
_lock = threading.Lock()


def _after_fork() -> None:
    # The parent's loop thread and lock cannot be used in the child.
    global _runner, _lock
    _runner = None
    _lock = threading.Lock()


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_after_fork)


def run_sync(coroutine: Coroutine[None, None, T]) -> T:
    """Run a coroutine from sync code, including inside a caller's running loop.

    Tasks inherit the caller's context variables. Calling from this helper's own
    thread is an error: async implementations must await their async counterparts.
    """
    global _runner
    try:
        with _lock:
            if _runner is None:
                _runner = _LoopThread()
            runner = _runner
        if threading.current_thread() is runner.thread:
            raise RuntimeError("Cannot call a Notte sync method from its event loop; await the async method instead.")
        future = asyncio.run_coroutine_threadsafe(coroutine, runner.loop)
    except BaseException:
        coroutine.close()
        raise
    try:
        return future.result()
    except BaseException:
        # In particular, Ctrl-C must not leave the browser operation running.
        _ = future.cancel()
        raise


def _shutdown() -> None:
    global _runner
    with _lock:
        runner, _runner = _runner, None
    if runner is not None:
        runner.close()


_ = atexit.register(_shutdown)
