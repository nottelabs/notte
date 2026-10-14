"""Exercise the readiness action without a live API or retry delays."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / ".github/actions/wait-for-api/wait-for-api.sh"
HEALTHY = {"status": "healthy", "version": "v1"}


class WaitForAPITests(unittest.TestCase):
    """Verify polling, streak resets, backoff, and the overall deadline."""

    def run_action(
        self,
        responses: list[dict[str, object]],
        *,
        timeout: int = 100,
        consecutive: int = 3,
        real_clock: bool = False,
    ) -> tuple[subprocess.CompletedProcess[str], list[dict[str, object]], list[int]]:
        """Run the real Bash action with scripted curl responses and a virtual sleep."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "responses.json").write_text(json.dumps(responses))
            curl = root / "curl"
            curl.write_text(
                f"#!{sys.executable}\n"
                """
import json
import os
import sys
import time
from pathlib import Path

root = Path(os.environ["POLL_FIXTURE"])
log = root / "polls.jsonl"
index = len(log.read_text().splitlines()) if log.exists() else 0
responses = json.loads((root / "responses.json").read_text())
if index >= len(responses):
    raise SystemExit("Unexpected extra health poll")
response = responses[index]
args = sys.argv[1:]
with log.open("a") as output:
    output.write(json.dumps({
        "max_time": int(args[args.index("--max-time") + 1]),
        "url": args[-1],
    }) + "\\n")
if response.get("delay"):
    time.sleep(response["delay"])
Path(args[args.index("-o") + 1]).write_text(
    response.get("raw", json.dumps(response.get("body", {})))
)
print(response.get("code", 200), end="")
sys.exit(response.get("exit", 0))
"""
            )
            curl.chmod(0o755)
            environment = {
                **os.environ,
                "PATH": f"{root}{os.pathsep}{os.environ['PATH']}",
                "POLL_FIXTURE": str(root),
                "API_URL": "https://api.example.test/",
                "TIMEOUT": str(timeout),
                "CONSECUTIVE": str(consecutive),
                "INTERVAL": "1",
                "MAX_BACKOFF": "4",
                "REAL_CLOCK": str(real_clock),
            }
            result = subprocess.run(
                [
                    "bash",
                    "-c",
                    """
if [ "$REAL_CLOCK" != "True" ]; then unset SECONDS; fi
SECONDS=0
sleep() {
    echo "$1" >> "$POLL_FIXTURE/sleeps"
    SECONDS=$((SECONDS + $1))
}
source "$1"
""",
                    "readiness-test",
                    str(SCRIPT),
                ],
                check=False,
                env=environment,
                text=True,
                capture_output=True,
                timeout=10,
            )
            poll_file = root / "polls.jsonl"
            polls = [json.loads(line) for line in poll_file.read_text().splitlines()] if poll_file.exists() else []
            sleep_file = root / "sleeps"
            sleeps = [int(line) for line in sleep_file.read_text().splitlines()] if sleep_file.exists() else []
            return result, polls, sleeps

    def test_stable_version_requires_consecutive_health(self) -> None:
        result, polls, sleeps = self.run_action([{"body": HEALTHY}] * 3)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(len(polls), 3)
        self.assertEqual(sleeps, [1, 1])
        self.assertTrue(all(poll["url"] == "https://api.example.test/health" for poll in polls))

    def test_version_change_restarts_streak(self) -> None:
        result, polls, _ = self.run_action([{"body": HEALTHY}] * 2 + [{"body": {**HEALTHY, "version": "v2"}}] * 3)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(len(polls), 5)
        self.assertIn("Version changed from v1 to v2", result.stdout)

    def test_failed_poll_resets_streak(self) -> None:
        failures: list[dict[str, object]] = [
            {"code": 503},
            {"code": "000", "exit": 28},
            {"raw": "not JSON"},
            {"body": {"status": "starting", "version": "v1"}},
            {"body": {"status": "healthy"}},
            {"body": {"status": "healthy", "version": ""}},
            {"body": {"status": "healthy", "version": None}},
        ]
        for failure in failures:
            with self.subTest(failure=failure):
                result, polls, _ = self.run_action([{"body": HEALTHY}] * 2 + [failure] + [{"body": HEALTHY}] * 3)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(len(polls), 6)
                self.assertIn("Streak broken after 2 healthy responses", result.stdout)

    def test_failed_polls_back_off_to_cap_and_health_resets_backoff(self) -> None:
        result, polls, sleeps = self.run_action(
            [{"code": 503}] * 4 + [{"body": HEALTHY}, {"code": 503}] + [{"body": HEALTHY}] * 3
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(len(polls), 9)
        self.assertEqual(sleeps, [1, 2, 4, 4, 1, 1, 1, 1])

    def test_timeout_stops_polling_and_caps_request_to_remaining_time(self) -> None:
        result, polls, sleeps = self.run_action([{"code": 503}] * 4, timeout=8)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual([poll["max_time"] for poll in polls], [8, 7, 5, 1])
        self.assertEqual(sleeps, [1, 2, 4])
        self.assertIn("was not ready within 8s", result.stdout)

    def test_long_deadline_caps_each_request_at_twenty_seconds(self) -> None:
        result, polls, _ = self.run_action([{"body": HEALTHY}], consecutive=1)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(polls[0]["max_time"], 20)

    def test_expired_deadline_never_polls(self) -> None:
        result, polls, sleeps = self.run_action([], timeout=0)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(polls, [])
        self.assertEqual(sleeps, [])

    def test_healthy_response_after_deadline_cannot_pass(self) -> None:
        result, polls, sleeps = self.run_action(
            [{"body": HEALTHY, "delay": 1.2}], timeout=1, consecutive=1, real_clock=True
        )
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(len(polls), 1)
        self.assertEqual(polls[0]["max_time"], 1)
        self.assertEqual(sleeps, [])
        self.assertNotIn("API is ready", result.stdout)


if __name__ == "__main__":
    unittest.main()
