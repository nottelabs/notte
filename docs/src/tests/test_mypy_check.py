"""Focused tests for ``mypy_check_code``.

The type-check job once passed for weeks without checking a single snippet: mypy
crashed on import, exited non-zero with an empty stdout, and the harness treated
"no diagnostic mentions the snippet" as success. These tests pin the contract that
makes that impossible: the only way to pass is a clean mypy exit, a snippet
diagnostic is a ``TypeError``, and anything else is a ``MypyNotRunError``.

``subprocess.run`` is replaced, so no mypy is needed and the tests run in every mode.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable

import pytest

from tests import test_snippets as ts

SNIPPET = "x: int = 'not an int'\n"


def _install_fake_mypy(
    monkeypatch: pytest.MonkeyPatch,
    *,
    returncode: int = 0,
    stdout: Callable[[str], str] | str = "",
    stderr: str = "",
    raise_timeout: bool = False,
) -> list[list[str]]:
    """Replace ``subprocess.run`` with a fake mypy; return the list of commands it saw."""
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(list(cmd))
        if raise_timeout:
            raise subprocess.TimeoutExpired(cmd, float(kwargs.get("timeout", 0) or 0))  # type: ignore[arg-type]
        tmp_path = cmd[3]  # python -m mypy <tmp_path> ...
        out = stdout(tmp_path) if callable(stdout) else stdout
        return subprocess.CompletedProcess(cmd, returncode, stdout=out, stderr=stderr)

    monkeypatch.setattr(ts.subprocess, "run", fake_run)
    return calls


def test_mypy_runs_through_the_test_interpreter_and_only_reports_the_snippet(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _install_fake_mypy(monkeypatch)
    ts.mypy_check_code(SNIPPET, "examples/ok.py")
    assert len(calls) == 1
    cmd = calls[0]
    assert cmd[:3] == [ts.sys.executable, "-m", "mypy"], "no nested `uv run`: it could re-sync the environment"
    assert "--follow-imports=silent" in cmd, "diagnostics from followed modules must not be attributed to the snippet"
    assert cmd[3].endswith(".py")


def test_clean_exit_passes_even_with_informational_notes(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_mypy(monkeypatch, returncode=0, stdout=lambda tmp: f"{tmp}:1:1: note: just saying\n")
    ts.mypy_check_code(SNIPPET, "examples/ok.py")


def test_snippet_diagnostic_is_a_type_error_pointing_at_the_source(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_mypy(
        monkeypatch,
        returncode=1,
        stdout=lambda tmp: f"{tmp}:1:10: error: Incompatible types in assignment  [assignment]\n",
    )
    with pytest.raises(TypeError) as exc:
        ts.mypy_check_code(SNIPPET, "examples/bad.py")
    message = str(exc.value)
    assert "Type checking failed for examples/bad.py" in message
    assert "examples/bad.py:1:10: error:" in message, "the temp path is rewritten to the tester path"


def test_snippet_diagnostic_matches_a_relative_or_realpath_form(monkeypatch: pytest.MonkeyPatch) -> None:
    import os

    _install_fake_mypy(
        monkeypatch,
        returncode=1,
        stdout=lambda tmp: f"{os.path.basename(tmp)}:2:1: error: boom  [misc]\n",
    )
    with pytest.raises(TypeError, match="examples/bad.py:2:1: error: boom"):
        ts.mypy_check_code(SNIPPET, "examples/bad.py")


def test_crash_with_empty_stdout_never_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    """The exact failure mode that hid 16 broken testers: import crash, exit 1, empty stdout."""
    _install_fake_mypy(
        monkeypatch,
        returncode=1,
        stdout="",
        stderr="ModuleNotFoundError: No module named 'pathspec.patterns.gitignore'",
    )
    with pytest.raises(ts.MypyNotRunError) as exc:
        ts.mypy_check_code(SNIPPET, "examples/ok.py")
    message = str(exc.value)
    assert "exit code 1" in message
    assert "pathspec.patterns.gitignore" in message, "stderr is surfaced so the job log explains itself"


def test_diagnostics_outside_the_snippet_never_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_mypy(
        monkeypatch,
        returncode=1,
        stdout="/somewhere/else/module.py:7:1: error: not the snippet  [misc]\n",
    )
    with pytest.raises(ts.MypyNotRunError, match="1 diagnostic\\(s\\) outside the snippet"):
        ts.mypy_check_code(SNIPPET, "examples/ok.py")


def test_usage_error_never_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_mypy(monkeypatch, returncode=2, stdout="", stderr="usage: mypy [-h] ...")
    with pytest.raises(ts.MypyNotRunError, match="exit code 2"):
        ts.mypy_check_code(SNIPPET, "examples/ok.py")


def test_timeout_never_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_mypy(monkeypatch, raise_timeout=True)
    with pytest.raises(ts.MypyNotRunError, match="timed out"):
        ts.mypy_check_code(SNIPPET, "examples/ok.py")
