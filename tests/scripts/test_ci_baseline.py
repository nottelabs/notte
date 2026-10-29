"""Missing, stale and partially rerun baselines cannot look complete."""

import json
import os
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from scripts.ci_baseline import Job, Run, assess, main


class BaselineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 10, 28, 12, tzinfo=timezone.utc)
        self.run: Run = {
            "id": 123,
            "head_sha": "a" * 40,
            "head_branch": "main",
            "event": "schedule",
            "status": "completed",
            "conclusion": "success",
            "updated_at": self.now.isoformat(),
            "html_url": "https://github.com/nottelabs/notte/actions/runs/123",
        }
        self.jobs: list[Job] = [
            {"name": name, "conclusion": "success"}
            for name in (
                "registered-examples / checks",
                "example-tests",
                "registered-examples / agent-models (openai-agents)",
                "registered-examples / agent-models (claude-agents)",
                "registered-examples / live (1/2)",
                "registered-examples / live (2/2)",
            )
        ]
        self.jobs.extend(
            {"name": f"registered-examples / native-checks ({index}/6)", "conclusion": "success"}
            for index in range(1, 7)
        )

    def test_complete_baseline(self) -> None:
        self.assertTrue(assess(self.run, self.jobs, 2, True, self.now)[1])

    def test_no_run(self) -> None:
        self.assertFalse(assess(None, [], 2, True, self.now)[1])

    def test_required_jobs_cannot_be_skipped_or_missing(self) -> None:
        for index in range(len(self.jobs)):
            with self.subTest(index=index):
                self.assertFalse(assess(self.run, self.jobs[:index] + self.jobs[index + 1 :], 2, True, self.now)[1])

    def test_successful_old_attempt_cannot_hide_latest_failure(self) -> None:
        self.jobs[-1]["conclusion"] = "failure"
        self.assertFalse(assess(self.run, self.jobs, 2, True, self.now)[1])

    def test_latest_run_must_finish_successfully(self) -> None:
        for status, conclusion in (("in_progress", None), ("completed", "failure"), ("completed", "cancelled")):
            with self.subTest(status=status, conclusion=conclusion):
                self.run.update(status=status, conclusion=conclusion)
                self.assertFalse(assess(self.run, self.jobs, 2, True, self.now)[1])

    def test_expired_or_future_timestamp(self) -> None:
        for delta in (timedelta(hours=-25), timedelta(hours=1)):
            with self.subTest(delta=delta):
                self.run["updated_at"] = (self.now + delta).isoformat()
                self.assertFalse(assess(self.run, self.jobs, 2, True, self.now)[1])

    def test_changed_harness_or_registry_is_not_current_coverage(self) -> None:
        self.assertFalse(assess(self.run, self.jobs, 2, False, self.now)[1])
        self.assertFalse(assess(self.run, self.jobs, 3, True, self.now)[1])

    def test_manual_or_other_branch_is_not_a_scheduled_full_run(self) -> None:
        self.run["event"] = "workflow_dispatch"
        self.assertFalse(assess(self.run, self.jobs, 2, True, self.now)[1])
        self.run.update(event="schedule", head_branch="feature")
        self.assertFalse(assess(self.run, self.jobs, 2, True, self.now)[1])

    def test_changed_selection_rules_invalidate_the_baseline(self) -> None:
        self.run["updated_at"] = datetime.now(timezone.utc).isoformat()
        for changed in (None, "scripts/ci_scope.py", ".github/actions/ci-scope/action.yml"):
            with self.subTest(changed=changed), TemporaryDirectory() as directory:

                def response(path: str) -> str:
                    if "/runs?" in path:
                        return json.dumps({"workflow_runs": [self.run]})
                    stale = changed is not None and f"/contents/{changed}?ref=" in path and "?ref=main" not in path
                    return json.dumps({"sha": "old" if stale else "current"})

                with (
                    patch.dict(
                        os.environ, GITHUB_REPOSITORY="fixture/repo", GITHUB_STEP_SUMMARY=f"{directory}/summary"
                    ),
                    patch("scripts.ci_baseline.api", side_effect=response),
                    patch(
                        "scripts.ci_baseline.subprocess.check_output", return_value=json.dumps([{"jobs": self.jobs}])
                    ),
                    patch.object(Path, "read_text", return_value="[{}, {}]"),
                ):
                    if changed:
                        with self.assertRaises(SystemExit):
                            main()
                    else:
                        main()
