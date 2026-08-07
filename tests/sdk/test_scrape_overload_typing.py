"""Run basedpyright and ty against scrape overload reveal_type cases."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CASES_DIR = REPO_ROOT / "typing_cases"
CASE_FILE = CASES_DIR / "scrape_overloads.py"

# Stable markers in typing_cases/scrape_overloads.py — order matters.
EXPECTED_REVEALS = (
    # RemoteSession
    "Profile",
    "dict[str, Any]",
    "list[ImageData]",
    "str",
    "str",
    "StructuredData[Profile]",
    # NotteClient
    "Profile",
    "dict[str, Any]",
    "list[ImageData]",
    "str",
    # PageClient
    "Profile",
    "dict[str, Any]",
    "list[ImageData]",
    "str",
    # NotteSession (local)
    "Profile",
    "dict[str, Any]",
    "list[ImageData]",
    "str",
)


def _normalize_type(text: str) -> str:
    cleaned = text.strip().strip("`").strip('"').strip("'")
    cleaned = cleaned.replace("typing.", "")
    # basedpyright sometimes prints fully-qualified names
    cleaned = re.sub(r"\b[\w.]+\.(\w+)\b", r"\1", cleaned)
    cleaned = cleaned.replace(" ", "")
    return cleaned


def _normalize_expected(text: str) -> str:
    return text.replace(" ", "")


def _extract_ty_reveals(output: str) -> list[str]:
    # info[revealed-type]: ... `Profile`
    return [_normalize_type(m) for m in re.findall(r"revealed-type.*?\n.*?`([^`]+)`", output, flags=re.S)]


def _extract_pyright_reveals(output: str) -> list[str]:
    # Type of "response_format" is "Profile"
    return [_normalize_type(m) for m in re.findall(r'Type of "[^"]+" is "([^"]+)"', output)]


def _run(cmd: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        check=False,
        text=True,
        capture_output=True,
    )


def _assert_reveals(actual: list[str], checker: str, raw: str) -> None:
    expected = [_normalize_expected(item) for item in EXPECTED_REVEALS]
    if actual != expected:
        raise AssertionError(
            f"{checker} scrape overload reveals mismatch.\n"
            f"expected ({len(expected)}): {expected}\n"
            f"actual   ({len(actual)}): {actual}\n"
            f"raw output:\n{raw}"
        )


@pytest.mark.order(1)
def test_scrape_overloads_with_ty() -> None:
    if shutil.which("ty") is None and shutil.which("uv") is None:
        pytest.skip("ty/uv not available")

    env = os.environ.copy()
    # Prefer the typing_cases ty.toml (extra-paths into workspace packages)
    env["TY_CONFIG_FILE"] = str(CASES_DIR / "ty.toml")

    cmd = ["uv", "run", "ty", "check", str(CASE_FILE)]
    result = _run(cmd, cwd=REPO_ROOT, env=env)
    combined = f"{result.stdout}\n{result.stderr}"
    # ty exits non-zero when it emits reveal_type infos in some versions; accept reveals either way
    reveals = _extract_ty_reveals(combined)
    if not reveals and result.returncode != 0:
        raise AssertionError(f"ty check failed without reveals:\n{combined}")
    _assert_reveals(reveals, "ty", combined)


@pytest.mark.order(1)
def test_scrape_overloads_with_basedpyright() -> None:
    cmd = ["uv", "run", "basedpyright", "--project", str(CASES_DIR), str(CASE_FILE)]
    result = _run(cmd, cwd=REPO_ROOT)
    combined = f"{result.stdout}\n{result.stderr}"
    # basedpyright may still report errors from imports; we only assert reveal lines
    reveals = _extract_pyright_reveals(combined)
    if not reveals:
        raise AssertionError(f"basedpyright produced no reveal_type lines:\n{combined}")
    _assert_reveals(reveals, "basedpyright", combined)
