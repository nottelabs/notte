"""Regression checks for the run-inspection documentation pairs."""

import os
import runpy
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from parser import parse_file

ROOT = Path(__file__).resolve().parents[1] / "testers/functions/management"


class RunInspectionPairsTest(unittest.TestCase):
    def test_display_ranges_hide_fixtures_and_preserve_output(self):
        for name, expected in (
            ("check_run_status", ("Status:", "Result:", "Session ID:")),
            ("high_failure_rate", ("Failed runs:", "Error:", "Time:", "only_active")),
        ):
            for suffix in ("py", "ts"):
                with self.subTest(name=name, language=suffix):
                    config, code = parse_file(ROOT / f"{name}.{suffix}")
                    self.assertIsNotNone(config.show)
                    for value in expected:
                        self.assertIn(value, code)
                    for hidden in ("assert", "FixtureClient", "NOTTE_FUNCTION_ID", "export", "matched ="):
                        self.assertNotIn(hidden, code)
                    if name == "high_failure_rate" and suffix == "ts":
                        self.assertIn("\n}\n```", code)

    def test_failed_runs_are_requested_and_inspected(self):
        failed = types.SimpleNamespace(
            function_run_id="owned-run", workflow_run_id="owned-run", status="failed", created_at="now"
        )
        requests = []
        inspected = []

        def list_runs(function_id, **options):
            requests.append((function_id, options))
            return types.SimpleNamespace(items=[failed] if options.get("only_active") is False else [])

        def get_run(function_id, run_id):
            inspected.append((function_id, run_id))
            return types.SimpleNamespace(result="Example function failure")

        client = types.SimpleNamespace(
            Function=lambda _: types.SimpleNamespace(run=lambda **kwargs: failed),
            functions=types.SimpleNamespace(list_runs=list_runs, get_run=get_run),
        )
        values = self.execute("high_failure_rate", client)
        self.assertEqual(values["results"], ["failed", True])
        self.assertEqual(requests, [("owned-function", {"only_active": False})])
        self.assertEqual(inspected, [("owned-function", "owned-run")] * 2)

    def test_status_example_rejects_a_different_run(self):
        for run_id in ("owned-run", "wrong-run"):
            with self.subTest(run_id=run_id):
                response = types.SimpleNamespace(
                    function_run_id=run_id,
                    status="closed",
                    session_id=None,
                    result='{"url": "https://example.com", "search_query": ""}',
                )
                client = types.SimpleNamespace(
                    Function=lambda _: types.SimpleNamespace(
                        run=lambda **kwargs: types.SimpleNamespace(function_run_id="owned-run")
                    ),
                    functions=types.SimpleNamespace(get_run=lambda *_: response),
                )
                if run_id == "owned-run":
                    self.assertEqual(self.execute("check_run_status", client)["run_id"], run_id)
                else:
                    with self.assertRaises(AssertionError):
                        self.execute("check_run_status", client)

    @staticmethod
    def execute(name, client):
        sdk = types.ModuleType("notte_sdk")
        sdk.NotteClient = lambda: client
        with (
            patch.dict("sys.modules", {"notte_sdk": sdk}),
            patch.dict(os.environ, {"NOTTE_FUNCTION_ID": "owned-function"}),
            patch("builtins.print"),
        ):
            return runpy.run_path(str(ROOT / f"{name}.py"))
