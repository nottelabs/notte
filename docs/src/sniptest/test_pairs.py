"""Offline regression tests for paired example generation and parity enforcement."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import generate
from catalog import catalog_sources
from parity import check_parity
from parser import parse_file


class RepositoryExamplesTest(unittest.TestCase):
    def test_agent_configuration_pairs_hide_setup_and_assertions(self):
        testers = Path(__file__).resolve().parents[1] / "testers/agents/config"
        cases = {
            "param_max_steps": "max_steps",
            "param_use_vision": "use_vision",
            "param_session": "open_viewer",
            "param_notifier": "Notifications can be configured in the Notte console",
        }
        for name, teaching_text in cases.items():
            for suffix in (".py", ".ts"):
                with self.subTest(name=name, language=suffix):
                    config, rendered = parse_file(testers / f"{name}{suffix}")
                    self.assertIsNotNone(config.show)
                    if suffix == ".ts" and name in ("param_session", "param_notifier", "creating_agent"):
                        self.assertIn("await client.Session", rendered)
                        self.assertIn("const agent = client.Agent", rendered)
                        self.assertNotIn("const agent = await", rendered)

                    self.assertIn(teaching_text, rendered)
                    self.assertIn("session", rendered)
                    for hidden in (
                        "import ",
                        "assert",
                        "export {",
                        "sessionStatus",
                        "status =",
                        "idle_timeout_minutes",
                    ):
                        self.assertNotIn(hidden, rendered)

    def test_python_page_examples_use_the_node_page_helper(self):
        root = Path(__file__).resolve().parents[1] / "testers"
        for path in root.rglob("*.ts"):
            python = path.with_suffix(".py")
            if python.exists() and "session.page" in python.read_text():
                with self.subTest(path=path):
                    self.assertNotIn("connectOverCDP", path.read_text())

    def test_playwright_cleanup_and_monitoring_pairs_preserve_teaching_code(self):
        testers = Path(__file__).resolve().parents[1] / "testers"
        for name in ("sessions/cdp/playwright_context_managers", "sessions/playwright-vs-notte/playwright_example"):
            for suffix in (".py", ".ts"):
                with self.subTest(name=name, language=suffix):
                    config, rendered = parse_file(testers / f"{name}{suffix}")
                    self.assertIsNotNone(config.show)
                    self.assertNotIn("export {", rendered)
                    self.assertNotIn("idle_timeout_minutes", rendered)
                    if suffix == ".py":
                        self.assertNotIn("status = session.status()", rendered)
                    if name.endswith("playwright_example"):
                        for text in ("Block images", "Listen to network requests", "https://example.com", "→", "←"):
                            self.assertIn(text, rendered)
                    else:
                        self.assertIn("Your code here", rendered)

    def test_cdp_pairs_keep_capture_and_serialization_out_of_python_docs(self):
        testers = Path(__file__).resolve().parents[1] / "testers/sessions/cdp"
        cases = {
            "playwright_events": "Listen to responses",
            "playwright_timeout": "Long Playwright automation",
            "playwright_cdp_error_handling": "CDP connection failed:",
            "selenium_javascript": "Result:",
            "selenium_playwright_alternative": "Title:",
        }
        for name, teaching_text in cases.items():
            for suffix in (".py", ".ts"):
                with self.subTest(name=name, language=suffix):
                    config, rendered = parse_file(testers / f"{name}{suffix}")
                    self.assertIsNotNone(config.show)
                    self.assertIn(teaching_text, rendered)
                    self.assertIn("from notte_sdk" if suffix == ".py" else "from 'notte-sdk'", rendered)
                    self.assertNotIn("export {", rendered)
                    self.assertNotIn("JSON.stringify", rendered)
                    self.assertNotIn("json.dumps", rendered)
                    if suffix == ".py":
                        self.assertNotIn("status = session.status()", rendered)
                    if name != "playwright_timeout":
                        self.assertNotIn("idle_timeout_minutes", rendered)
                    else:
                        self.assertIn("idle_timeout_minutes", rendered)
                        self.assertIn("max_duration_minutes", rendered)

    def test_create_session_tabs_show_the_same_task_and_output(self):
        testers = Path(__file__).resolve().parents[1] / "testers/sessions/lifecycle"
        for name in ("create_session", "create_session_2"):
            _, python = parse_file(testers / f"{name}.py")
            _, typescript = parse_file(testers / f"{name}.ts")
            with self.subTest(name=name):
                for code in (python, typescript):
                    self.assertIn("Session ", code)
                    self.assertIn(" is active", code)
                    self.assertIn("https://example.com", code)
                self.assertEqual("Page title:" in python, "Page title:" in typescript)
                self.assertNotIn("console.log(viewport)", typescript)
                self.assertNotIn("page.evaluate", typescript)
                if name == "create_session":
                    self.assertNotIn("Session is not active", typescript)
                    for code in (python, typescript):
                        self.assertIn("1920", code)
                        self.assertIn("1080", code)

    def test_non_timeout_examples_do_not_configure_idle_timeouts(self):
        testers = Path(__file__).resolve().parents[1] / "testers"
        for name in (
            "sessions/configuration/proxies_simple",
            "sessions/configuration/quick_start",
            "sessions/configuration/viewport",
            "sessions/lifecycle/create_session",
            "sessions/lifecycle/create_session_2",
            "sessions/lifecycle/monitor_state",
            "sessions/lifecycle/stop_session",
            "sessions/lifecycle/error_handling",
            "sessions/lifecycle/error_handling_2",
        ):
            for suffix in (".py", ".ts"):
                with self.subTest(name=name, language=suffix):
                    self.assertNotIn("idle_timeout_minutes", (testers / f"{name}{suffix}").read_text())

    def test_all_new_pairs_keep_test_plumbing_out_of_displayed_code(self):
        directory = Path(__file__).resolve().parent
        contracts = json.loads((directory / "live-examples.json").read_text())
        for name in contracts:
            for suffix in (".py", ".ts"):
                path = (directory.parent / "testers" / name).with_suffix(suffix)
                with self.subTest(path=path):
                    config, rendered = parse_file(path)
                    self.assertIsNotNone(config.show)
                    for unwanted in (
                        "NOTTE_FUNCTION_ID",
                        "same_run",
                        "export {",
                        "Values retained",
                    ):
                        self.assertNotIn(unwanted, rendered)
                    if name == "browser-controls/eval_js.ts" and suffix == ".py":
                        # JSON parsing is the original lesson, not test serialization.
                        self.assertIn("import json", rendered)
                        self.assertIn("json.loads(session.evaluate_js", rendered)
                    else:
                        self.assertNotIn("import json", rendered)
                    if name == "sessions/capabilities/dev_environment.ts" and suffix == ".py":
                        # This lesson intentionally teaches environment-dependent
                        # viewer configuration; os is teaching code, not a fixture.
                        self.assertIn('os.getenv("ENV") == "development"', rendered)
                        self.assertIn("open_viewer=is_dev", rendered)
                    else:
                        self.assertNotIn("import os", rendered)
                    self.assertNotIn("json.dumps", path.read_text())
                    self.assertNotIn("JSON.stringify", path.read_text())

    def test_focused_function_examples_hide_execution_setup_in_both_tabs(self):
        testers = Path(__file__).resolve().parents[1] / "testers/functions/invocations"
        for name in ("check_run_status", "sequential"):
            for suffix in (".py", ".ts"):
                with self.subTest(name=name, language=suffix):
                    path = testers / f"{name}{suffix}"
                    config, rendered = parse_file(path)
                    self.assertIsNotNone(config.show)
                    self.assertNotIn("import ", rendered)
                    self.assertNotIn("NOTTE_FUNCTION_ID", rendered)
                    self.assertNotIn("same_run", rendered)
                    self.assertNotIn("json.dumps", rendered)
                    self.assertNotIn("JSON.stringify", rendered)
                    if name == "check_run_status":
                        self.assertIn("Status:", rendered)
                        self.assertIn("Result:", rendered)
                        self.assertIn("get_run(run_id)" if suffix == ".py" else "getRun(runId)", rendered)
                    else:
                        self.assertIn("print(results)" if suffix == ".py" else "console.log(results)", rendered)

    def test_paired_python_examples_compile(self):
        testers = Path(__file__).resolve().parents[1] / "testers"
        pairs = list(testers.rglob("*.ts"))
        self.assertTrue(pairs, "At least one executable pair is required")
        for typescript in pairs:
            if typescript.resolve() in catalog_sources(testers):
                continue
            python = typescript.with_suffix(".py")
            with self.subTest(path=python):
                compile(python.read_text(), str(python), "exec")


class PairedExamplesTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.testers = self.root / "testers"
        self.testers.mkdir()
        self.python = self.testers / "example.py"
        self.python.write_text('# @sniptest filename=example.py\nprint("hello")\n')
        for name, value in [
            ("ROOT_DIR", self.root),
            ("TESTERS_DIR", self.testers),
            ("SNIPPETS_DIR", self.root / "snippets"),
        ]:
            mock = patch.object(generate, name, value)
            mock.start()
            self.addCleanup(mock.stop)

    def pair(self):
        self.python.with_suffix(".ts").write_text(
            '// @sniptest filename=example.ts\n// @sniptest show=2-2\n// setup\nconsole.log("hello");\n'
        )

    def test_python_output_is_unchanged(self):
        self.assertEqual(
            generate.render_file(self.python), generate.make_header("testers/example.py") + parse_file(self.python)[1]
        )

    def test_pair_has_independent_show_range_and_languages(self):
        self.pair()
        rendered = generate.render_file(self.python)
        self.assertIn("<CodeGroup>", rendered)
        self.assertIn('```python example.py\nprint("hello")', rendered)
        self.assertIn('```typescript example.ts\nconsole.log("hello");', rendered)
        self.assertNotIn("// setup", rendered)
        self.assertNotIn("// @sniptest", rendered)

    def test_check_detects_drift_without_writing(self):
        self.pair()
        output = generate.get_output_path(self.python)
        self.assertFalse(generate.process_file(self.python, check=True)[0])
        self.assertFalse(output.exists())
        self.assertTrue(generate.process_file(self.python)[0])
        original = output.read_text()
        self.assertTrue(generate.process_file(self.python, check=True)[0])
        self.python.with_suffix(".ts").write_text('console.log("changed");\n')
        self.assertFalse(generate.process_file(self.python, check=True)[0])
        self.assertEqual(output.read_text(), original)

    def test_manual_pair_is_rejected(self):
        self.pair()
        output = generate.get_output_path(self.python)
        output.parent.mkdir()
        output.write_text("manual snippet")
        self.assertFalse(generate.process_file(self.python, check=True)[0])

    def test_missing_and_orphan_counterparts_fail(self):
        manifest = {"unpaired": [], "python_only": {}}
        self.assertIn("Missing TypeScript counterpart: example.py", check_parity(self.testers, manifest))
        self.pair()
        self.assertEqual(check_parity(self.testers, manifest), [])
        self.python.unlink()
        self.assertIn("Missing Python counterpart: example.ts", check_parity(self.testers, manifest))

    def test_backlog_cannot_grow_and_paired_entries_must_be_removed(self):
        manifest = {"unpaired": ["example.py"], "python_only": {}}
        self.assertEqual(check_parity(self.testers, manifest, manifest), [])
        self.assertIn(
            "Migration backlog cannot grow: example.py", check_parity(self.testers, manifest, {"unpaired": []})
        )
        self.pair()
        self.assertIn("Remove stale backlog/exception entry: example.py", check_parity(self.testers, manifest))

    def test_exceptions_require_reasons(self):
        self.assertTrue(check_parity(self.testers, {"unpaired": [], "python_only": {"example.py": ""}}))
        self.assertEqual(
            check_parity(
                self.testers,
                {"unpaired": [], "python_only": {"example.py": "Python runtime handler, not an SDK client"}},
            ),
            [],
        )


if __name__ == "__main__":
    unittest.main()
