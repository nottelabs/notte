"""A running function must not be able to spawn a process.

The runner allows ``asyncio`` (functions use it for concurrency), and asyncio is
the one route to a subprocess the import allow list leaves reachable.
``deny_subprocess_creation`` closes it around the user-code ``exec`` and, being
scoped, restores process creation afterwards so the runner's own forkserver and
an SDK host process keep working.
"""

import subprocess

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


def test_the_guard_restores_afterwards() -> None:
    # A scoped guard must leave the host process able to spawn again - the SDK
    # runs a local function inside the caller's own interpreter.
    original = subprocess.Popen
    with deny_subprocess_creation():
        with pytest.raises(SubprocessNotAllowed):
            subprocess.Popen(["true"])
    assert subprocess.Popen is original
