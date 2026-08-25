"""A running function must not spawn a process, and the guard must not corrupt
the host process that ran it.

The runner allows ``asyncio`` (functions use it for concurrency), and asyncio is
the one route to a subprocess the import allow list leaves reachable.
``deny_subprocess_creation`` closes it around the user-code ``exec``. It is
reentrant: overlapping local runs share one patch and restore only when the last
finishes, so neither corrupts the other's view of ``subprocess``. It is a
defense-in-depth layer - a function that defers a spawn to a thread outliving the
run still reaches the real ``subprocess`` - which is why the runner that executes
untrusted code denies subprocess permanently in a single-use child instead.
"""

import subprocess
import threading
import time

import pytest
from notte_core.ast import SecureScriptRunner, SubprocessNotAllowed, deny_subprocess_creation


class _StubNotteModule:
    def __getattr__(self, name: str) -> object:
        raise RuntimeError(f"notte.{name} is not available in this test")


def _run(body: str, *, restricted: bool) -> object:
    return SecureScriptRunner(_StubNotteModule()).run_script(body, restricted=restricted)  # pyright: ignore [reportArgumentType]


_CREATE_SUBPROCESS_SHELL = """
import asyncio
async def go():
    p = await asyncio.create_subprocess_shell("echo escaped", stdout=-1)
    out, _ = await p.communicate()
    return out
return asyncio.run(go())
"""

_MAKE_SUBPROCESS_TRANSPORT = """
import asyncio
async def go():
    loop = asyncio.get_event_loop()
    return await loop._make_subprocess_transport(
        asyncio.SubprocessProtocol(), "echo x", True, -1, -1, -1, None
    )
return asyncio.run(go())
"""

_TO_THREAD = """
import asyncio
return asyncio.run(asyncio.to_thread(lambda: 2 + 2))
"""


def _as_run(body: str) -> str:
    import textwrap

    return "def run():\n" + textwrap.indent(textwrap.dedent(body).strip() + "\n", "    ")


def test_unrestricted_subprocess_is_blocked() -> None:
    with pytest.raises(RuntimeError, match="not permitted"):
        _run(_as_run(_CREATE_SUBPROCESS_SHELL), restricted=False)


def test_unrestricted_low_level_transport_is_blocked() -> None:
    with pytest.raises(RuntimeError, match="not permitted"):
        _run(_as_run(_MAKE_SUBPROCESS_TRANSPORT), restricted=False)


def test_unrestricted_concurrency_still_works() -> None:
    assert _run(_as_run(_TO_THREAD), restricted=False) == 4


def test_guard_restores_the_host_afterwards() -> None:
    original = subprocess.Popen
    with deny_subprocess_creation():
        with pytest.raises(SubprocessNotAllowed):
            subprocess.Popen(["true"])
    assert subprocess.Popen is original


def test_nested_guards_hold_until_the_outermost_exits() -> None:
    original = subprocess.Popen
    with deny_subprocess_creation():
        with deny_subprocess_creation():
            assert subprocess.Popen is not original
        # Inner exit must NOT restore while the outer guard is still active.
        assert subprocess.Popen is not original
    assert subprocess.Popen is original


def test_overlapping_guards_across_threads_do_not_corrupt_the_host() -> None:
    original = subprocess.Popen
    errors: list[str] = []

    def worker(hold: float) -> None:
        try:
            with deny_subprocess_creation():
                time.sleep(hold)
                # While any guard is active, the host must still be denied - a
                # sibling's exit must not restore the real Popen underneath us.
                assert subprocess.Popen is not original
        except AssertionError as exc:  # noqa: PERF203
            errors.append(str(exc))

    threads = [threading.Thread(target=worker, args=(hold,)) for hold in (0.3, 0.1)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors
    assert subprocess.Popen is original
