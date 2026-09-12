"""Keep caller-side function lessons paired without exposing live fixtures."""

import json
import unittest
from pathlib import Path

from parser import parse_file

ROOT = Path(__file__).resolve().parents[1]
NAMES = (
    "invoke_function",
    "batch_invocation",
    "monitor_runs",
    "invocations/timeout_examples",
    "management/check_run_status",
    "management/version_management",
)


class FunctionInvocationPairsTest(unittest.TestCase):
    def test_live_contracts_and_hidden_fixtures(self):
        contracts = json.loads((ROOT / "sniptest/live-examples.json").read_text())
        for name in NAMES:
            self.assertIn(f"functions/{name}.ts", contracts)
            for suffix in (".py", ".ts"):
                with self.subTest(name=name, language=suffix):
                    config, rendered = parse_file(ROOT / "testers/functions" / f"{name}{suffix}")
                    self.assertIsNotNone(config.show)
                    for hidden in ("NOTTE_FUNCTION_ID", "FixtureClient", "assert", "export {", "import os"):
                        self.assertNotIn(hidden, rendered)

    def test_parallel_invocation_preserves_inputs_and_output(self):
        for suffix in (".py", ".ts"):
            _, rendered = parse_file(ROOT / "testers/functions" / f"batch_invocation{suffix}")
            for url in ("https://site1.com", "https://site2.com", "https://site3.com"):
                self.assertIn(url, rendered)
            self.assertIn("result.result", rendered)
            self.assertIn("ThreadPoolExecutor(max_workers=3)" if suffix == ".py" else "Promise.all", rendered)

    def test_timeout_units_and_monitoring_behavior(self):
        for suffix in (".py", ".ts"):
            _, timeout = parse_file(ROOT / "testers/functions/invocations" / f"timeout_examples{suffix}")
            for limit in (60, 600):
                self.assertIn(f"timeout={limit})" if suffix == ".py" else f"timeoutMs: {limit}_000", timeout)
            _, monitor = parse_file(ROOT / "testers/functions" / f"monitor_runs{suffix}")
            self.assertIn("stream=False" if suffix == ".py" else "stream: false", monitor)
            for text in ("Status:", "Final result:", "closed", "failed", "Check every 5 seconds"):
                self.assertIn(text, monitor)

    def test_run_inspection_and_version_lessons_preserve_output(self):
        for suffix in (".py", ".ts"):
            _, run = parse_file(ROOT / "testers/functions/management" / f"check_run_status{suffix}")
            for text in ("Status:", "Result:", "Session ID:"):
                self.assertIn(text, run)
            _, versions = parse_file(ROOT / "testers/functions/management" / f"version_management{suffix}")
            for text in ("Available versions:", "Latest:", "latest_version", "versions"):
                self.assertIn(text, versions)
