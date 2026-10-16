"""Run basedpyright against the generated execute() overloads (typing_cases/execute_overloads.py)."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CASES_DIR = REPO_ROOT / "typing_cases"
CASE_FILE = CASES_DIR / "execute_overloads.py"


def test_execute_overloads_accept_exposed_actions_and_reject_the_rest() -> None:
    result = subprocess.run(
        ["uv", "run", "basedpyright", "--project", str(CASES_DIR), str(CASE_FILE)],
        cwd=REPO_ROOT,
        check=False,
        text=True,
        capture_output=True,
    )
    output = f"{result.stdout}\n{result.stderr}"
    if not re.search(r"\d+ errors?, \d+ warnings?", output):
        raise AssertionError(f"basedpyright did not run:\n{output}")

    reported = {int(line) for line in re.findall(rf"{re.escape(CASE_FILE.name)}:(\d+):\d+ - error", output)}
    expected = {
        number
        for number, line in enumerate(CASE_FILE.read_text().splitlines(), start=1)
        if line.rstrip().endswith("# expect-error")
    }
    assert expected, "no `# expect-error` cases"
    assert reported == expected, f"errors on lines {sorted(reported)}, expected {sorted(expected)}:\n{output}"
