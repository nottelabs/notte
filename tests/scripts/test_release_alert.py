"""Execute release alert serialization offline, without posting a notification."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/nightly-test-release.yml"


def steps():
    return {step["name"]: step for step in yaml.safe_load(WORKFLOW.read_text())["jobs"]["example-tests"]["steps"]}


@pytest.mark.parametrize(
    "output,expected",
    [
        (
            'HTTP 500: "scrape failed"\\path\nline\ttab\rreturn\x00\x01\x1b[31mred\x1b[0m',
            'HTTP 500: "scrape failed"\\path\nline\ttab\rreturn\x00\x01red',
        ),
        ("Unicode: é 💥 and ${untrusted} $() `text`", "Unicode: é 💥 and ${untrusted} $() `text`"),
        ("x" * 16000, "x" * 12000),
        ("", ""),
    ],
    ids=["controls", "unicode", "bounded-output", "empty-output"],
)
def test_payload_round_trips_errors_controls_and_bounded_output(tmp_path: Path, output: str, expected: str) -> None:
    command = steps()["Prepare error message"]["run"]
    result = subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", command],
        cwd=tmp_path,
        env={
            "PATH": str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"],
            "TEST_OUTPUT": output.replace("\x00", ""),
            "RUN_TIMESTAMP": '123"\\',
            "RUN_URL": "https://github.com/nottelabs/notte/actions/runs/123",
        },
        capture_output=True,
        text=True,
        timeout=10,
    )
    # Environment values cannot contain NUL; all other control characters are tested.
    expected = expected.replace("\x00", "")
    assert result.returncode == 0, result.stderr
    raw = (tmp_path / "slack-payload.json").read_text()
    payload = json.loads(raw)
    assert payload["username"] == 'GitHub Nightly Release Pipeline (123"\\)'
    assert payload["text"] == (
        "❌ Nightly Release Pipeline FAILED: <https://github.com/nottelabs/notte/actions/runs/123|View Pipeline Run>"
        f"\n```\n{expected}\n```"
    )
    assert "\x1b[" not in payload["text"]
    assert not any(ord(char) < 32 for char in raw)


def test_notification_keeps_failure_condition_and_original_test_propagation() -> None:
    config = steps()
    condition = "steps.test_release.outcome == 'failure' && env.SLACK_NIGHTLY_WEBHOOK_URL != ''"
    assert config["Prepare error message"]["if"] == condition
    send = config["Send Slack Notification on Failure"]
    assert send["if"] == condition
    assert send["with"]["payload-file-path"] == "slack-payload.json"
    assert "payload" not in send["with"]
    assert config["Run test release"]["run"] == "bash scripts/test_release.sh"
    propagate = config["Propagate release test failure"]
    assert propagate["if"] == "steps.test_release.outcome == 'failure'"
    result = subprocess.run(["bash", "-c", propagate["run"]], timeout=5)
    assert result.returncode == 1
