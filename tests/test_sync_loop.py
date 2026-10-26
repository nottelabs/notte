import asyncio
import concurrent.futures
import contextvars
import subprocess
import sys
import threading
from unittest.mock import patch

import notte_core
import pytest
from notte_core._sync import run_sync


async def loop_and_context(value: contextvars.ContextVar[str]) -> tuple[asyncio.AbstractEventLoop, str]:
    await asyncio.sleep(0)
    return asyncio.get_running_loop(), value.get()


def test_sync_calls_share_loop_and_copy_each_callers_context() -> None:
    value = contextvars.ContextVar("value", default="default")
    value.set("first")
    loop, result = run_sync(loop_and_context(value))
    assert result == "first"
    value.set("second")
    assert run_sync(loop_and_context(value)) == (loop, "second")
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:

        def call(index: int) -> tuple[asyncio.AbstractEventLoop, str]:
            value.set(str(index))
            return run_sync(loop_and_context(value))

        assert list(pool.map(call, range(8))) == [(loop, str(index)) for index in range(8)]
    assert value.get() == "second"


@pytest.mark.asyncio
async def test_sync_call_inside_running_loop_does_not_patch_asyncio() -> None:
    caller_loop = asyncio.get_running_loop()
    original_run = asyncio.run
    async with asyncio.timeout(5):
        loop, _ = run_sync(loop_and_context(contextvars.ContextVar("value", default="ok")))
        assert loop is not caller_loop
        await asyncio.sleep(0)
    assert asyncio.run is original_run
    with pytest.raises(RuntimeError, match="cannot be called from a running event loop"):
        coroutine = asyncio.sleep(0)
        try:
            asyncio.run(coroutine)
        finally:
            coroutine.close()


def test_reentrant_sync_call_fails_instead_of_deadlocking() -> None:
    async def nested() -> None:
        run_sync(asyncio.sleep(0))

    with pytest.raises(RuntimeError, match="await the async method"):
        run_sync(nested())


def test_exceptions_propagate_and_next_call_still_works() -> None:
    async def fail() -> None:
        raise ValueError("operation failed")

    with pytest.raises(ValueError, match="operation failed"):
        run_sync(fail())
    assert run_sync(asyncio.sleep(0, result=42)) == 42


def test_interrupt_cancels_background_operation() -> None:
    started, cancelled = threading.Event(), threading.Event()

    async def operation() -> None:
        try:
            started.set()
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    def interrupt(_future: concurrent.futures.Future[None]) -> None:
        assert started.wait(5)
        raise KeyboardInterrupt

    with patch.object(concurrent.futures.Future, "result", interrupt):
        with pytest.raises(KeyboardInterrupt):
            run_sync(operation())
    assert cancelled.wait(5)
    assert run_sync(asyncio.sleep(0, result=42)) == 42


def test_imports_leave_asyncio_untouched_and_do_not_start_thread() -> None:
    subprocess.run(
        [
            sys.executable,
            "-c",
            """
import asyncio, threading
original = asyncio.run
import notte_sdk, notte_browser.session
assert asyncio.run is original
assert not any(thread.name == 'notte-sync' for thread in threading.enumerate())
""",
        ],
        check=True,
        timeout=20,
    )


def test_deprecated_nest_asyncio_hook_is_a_noop() -> None:
    original = asyncio.run
    with pytest.warns(DeprecationWarning, match="has no effect"):
        notte_core.enable_nest_asyncio()
    assert not notte_core.nest_asyncio_enabled
    assert asyncio.run is original


def test_concurrent_first_calls_start_one_loop_and_shutdown_cleans_tasks() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import asyncio, concurrent.futures, threading
from notte_core._sync import run_sync
barrier = threading.Barrier(8)
async def current_loop():
    return id(asyncio.get_running_loop())
def call(_):
    barrier.wait()
    return run_sync(current_loop())
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
    assert len(set(pool.map(call, range(8)))) == 1
assert sum(thread.name == 'notte-sync' for thread in threading.enumerate()) == 1
async def pending():
    try:
        await asyncio.Event().wait()
    finally:
        print('pending task cleaned up', flush=True)
async def start_pending():
    asyncio.create_task(pending())
    await asyncio.sleep(0)
run_sync(start_pending())
""",
        ],
        check=True,
        timeout=20,
        capture_output=True,
        text=True,
    )
    assert "pending task cleaned up" in result.stdout


@pytest.mark.asyncio
async def test_base_vault_and_persona_sync_methods_inside_running_loop() -> None:
    from tests.mock.mock_vault import MockVault
    from tests.test_session_persona_helpers import StubPersona

    vault = MockVault()
    vault.add_credentials("example.com", username="ada")
    assert vault.get_credentials("example.com")["username"] == "ada"
    assert vault.has_credential("example.com")
    vault.delete_credentials("example.com")
    assert not vault.has_credential("example.com")
    persona = StubPersona(emails=[], sms=[])
    assert persona.emails() == []
    assert persona.sms() == []
