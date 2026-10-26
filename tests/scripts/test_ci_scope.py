"""Offline routing contracts, including real Git history and CLI output."""

from __future__ import annotations

import contextlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import ci_integration_examples as runner
from scripts import ci_scope as ci

ROOT = Path(__file__).resolve().parents[2]


class RoutingTests(unittest.TestCase):
    # Fixed expectations describe the historical seven-owner migration.
    @patch.object(
        ci,
        "INTEGRATION_EXAMPLES",
        json.loads((ROOT / "tests/scripts/fixtures/integration_example_commands.json").read_text())["active"],
    )
    def test_shipped_native_recipe_and_project_inputs_keep_required_paired_owner(self) -> None:
        inputs = {
            "docs/src/testers/integrations/openai_agents.py": {"openai-agents"},
            "docs/src/testers/integrations/claude_agents.ts": {"claude-agents"},
            "docs/src/testers/integrations/agent_browser.py": {"agent-browser"},
            "node-sdk/test/helpers/run-openai-recipe.py": {"openai-agents"},
            "node-sdk/test/agent-browser.recipe.test.ts": {"agent-browser"},
            "tests/docs/test_agent_browser_recipe.py": {"agent-browser"},
            "docs/package-lock.json": {"openai-agents", "claude-agents"},
            ".github/workflows/selector-repair.yml": {"github-actions"},
            "docs/src/integrations/github-actions.mdx": {"github-actions"},
            "examples/trigger/src/read-page.ts": {"trigger"},
            "examples/inngest/src/index.ts": {"inngest"},
            "examples/temporal/test/workflow.live.test.ts": {"temporal"},
        }
        for path, expected in inputs.items():
            with self.subTest(path=path):
                self.assertEqual(ci.integration_examples_for_path(path), expected)
                self.assertTrue(ci.GROUPS["paired"] <= ci.scopes_for_path(path))
                self.assertTrue(ci.base_scopes_for_path(path) <= ci.scopes_for_path(path))
        for name in (
            "agent-browser",
            "claude-agents",
            "github-actions",
            "inngest",
            "openai-agents",
            "temporal",
            "trigger",
        ):
            path = f".github/workflows/{name}-integration.yml"
            with self.subTest(path=path):
                self.assertEqual(ci.integration_examples_for_path(path), {name})
                self.assertTrue(ci.GROUPS["paired"] <= ci.scopes_for_path(path))

    def test_prose_never_selects_live_suites(self) -> None:
        for path in (
            "docs/src/pricing.mdx",
            "docs/src/features/sessions/proxies.mdx",
            "docs/src/llms.txt",
            "docs/src/sdk-reference/session.mdx",
            "docs/src/images/logo.svg",
            "docs/src/docs.json",
            "README.md",
            "node-sdk/README.md",
            "node-sdk/CHANGELOG.md",
            "packages/notte-sdk/README.md",
        ):
            with self.subTest(path=path):
                selected = ci.scopes_for_path(path, code_changed=False)
                self.assertFalse({name for name in selected if name.endswith("_live")}, selected)
                self.assertNotIn("cli_contract", selected)
                self.assertNotIn("python_unit", selected)
                self.assertNotIn("node_generated", selected)

    def test_python_unit_and_integration_changes_are_separate(self) -> None:
        self.assertEqual(ci.scopes_for_path("tests/browser/test_window.py"), {"python_static", "python_unit"})
        self.assertEqual(ci.scopes_for_path("tests/integration/sdk/test_session.py"), ci.PYTHON_RUNTIME)
        self.assertEqual(ci.scopes_for_path("tests/docs/test_pricing_docs.py"), {"python_static", "python_docs"})
        for path in ("tests/conftest.py", "tests/data/cookies.json", "tests/mock/mock_service.py"):
            with self.subTest(path=path):
                self.assertTrue(ci.PYTHON_RUNTIME <= ci.scopes_for_path(path))

    def test_marked_live_tests_outside_integration_keep_live_coverage(self) -> None:
        marked = {
            path.relative_to(ROOT).as_posix()
            for path in (ROOT / "tests").rglob("test_*.py")
            if not path.is_relative_to(ROOT / "tests/integration")
            and re.search(r"pytest\.mark\.(?:live|staging)\b", path.read_text())
        }
        self.assertEqual(ci.PYTHON_LIVE_TESTS, marked)
        self.assertIn("tests/test_fetch_helper.py", marked)
        for path in marked:
            with self.subTest(path=path):
                self.assertTrue(ci.PYTHON_RUNTIME <= ci.scopes_for_path(path))

    def test_shared_pytest_configuration_keeps_readme_example_validation(self) -> None:
        for path in ("tests/conftest.py", "tests/test_notte_config.toml"):
            with self.subTest(path=path):
                selected = ci.scopes_for_path(path)
                self.assertTrue(ci.PYTHON_RUNTIME <= selected)
                self.assertTrue(ci.GROUPS["readme"] <= selected)

    def test_python_runtime_and_prompt_changes_keep_live_coverage(self) -> None:
        for path in (
            "packages/notte-core/src/notte_core/observation.py",
            "packages/notte-core/src/notte_core/prompts/system.md",
            "packages/notte-browser/src/notte_browser/playwright.py",
            "packages/notte-browser/pyproject.toml",
            "src/notte/__init__.py",
        ):
            with self.subTest(path=path):
                self.assertTrue(ci.PYTHON_RUNTIME <= ci.scopes_for_path(path))
        browser = ci.scopes_for_path("packages/notte-browser/src/notte_browser/playwright.py")
        self.assertNotIn("paired_live", browser)
        self.assertNotIn("node_generated", browser)
        sdk = ci.scopes_for_path("packages/notte-sdk/src/notte_sdk/client.py")
        self.assertTrue(ci.SDK_EXAMPLES <= sdk)

    def test_cli_matrix_only_runs_for_contract_inputs(self) -> None:
        for path in (
            "notte-cli",
            "packages/notte-sdk/src/notte_sdk/auth.py",
            "tests/sdk/test_cli_keyring_contract.py",
            "tests/sdk/cli_contract/keyring.go",
            "pyproject.toml",
            "uv.lock",
            ".python-version",
            "packages/notte-sdk/pyproject.toml",
        ):
            with self.subTest(path=path):
                self.assertIn("cli_contract", ci.scopes_for_path(path))
        self.assertNotIn("cli_contract", ci.scopes_for_path("packages/notte-sdk/src/notte_sdk/endpoints/sessions.py"))

    def test_node_unit_changes_do_not_wake_staging(self) -> None:
        self.assertEqual(ci.scopes_for_path("node-sdk/test/client.test.ts"), {"node_static"})
        self.assertIn("node_live", ci.scopes_for_path("node-sdk/test/session.integration.test.ts"))
        self.assertIn("node_live", ci.scopes_for_path("node-sdk/test/integration.test.ts"))
        self.assertIn("paired_live", ci.scopes_for_path("node-sdk/test/helpers/docs-examples.ts"))

    def test_staging_drift_check_only_runs_for_generation_inputs(self) -> None:
        for path in (
            "node-sdk/src/lib/client/types.gen.ts",
            "node-sdk/src/resources.gen.ts",
            "node-sdk/src/proxy/patterns.ts",
            "node-sdk/scripts/normalize-generated.js",
            "node-sdk/openapi-ts.config.ts",
            "node-sdk/package.json",
            "node-sdk/package-lock.json",
        ):
            with self.subTest(path=path):
                self.assertIn("node_generated", ci.scopes_for_path(path))
        self.assertNotIn("node_generated", ci.scopes_for_path("node-sdk/src/session.ts"))
        self.assertNotIn("node_generated", ci.scopes_for_path("node-sdk/scripts/generate-reference.mjs"))
        self.assertIn("node_generated", ci.scopes_for_path("node-sdk/new-generator.config.json"))

    def test_executable_docs_and_readme_changes_keep_live_checks(self) -> None:
        for path in (
            "docs/src/testers/sessions/index.py",
            "docs/src/testers/sessions/index.ts",
            "docs/src/testers/snippets.json",
            "docs/src/tests/test_snippets.py",
            "docs/src/conftest.py",
        ):
            with self.subTest(path=path):
                self.assertIn("docs_live", ci.scopes_for_path(path))
        self.assertIn("paired_live", ci.scopes_for_path("docs/src/sniptest/run_python.py"))
        self.assertIn("readme_live", ci.scopes_for_path("README.md", code_changed=True))
        self.assertIn("docs_live", ci.scopes_for_path("docs/src/guides/example.mdx", code_changed=True))

    def test_native_projects_route_into_existing_paired_jobs(self) -> None:
        for path in (
            "examples/openai-computer-use/python/demo.py",
            "examples/openai-computer-use/typescript/test/computer.live.test.ts",
            "examples/openai-computer-use/pyproject.toml",
            "examples/openai-computer-use/uv.lock",
            "examples/openai-computer-use/typescript/package-lock.json",
            "examples/openai-computer-use/fixtures/mouse.html",
        ):
            with self.subTest(path=path):
                self.assertTrue(ci.GROUPS["paired"] <= ci.scopes_for_path(path))
                self.assertEqual(ci.integration_examples_for_path(path), {"openai-computer-use"})
        for path in ("examples/openai-computer-use/README.md", "examples/openai-computer-use/.gitignore"):
            self.assertFalse(ci.integration_examples_for_path(path))
            self.assertNotIn("paired_live", ci.scopes_for_path(path))

    def test_gemini_native_inputs_preserve_root_commands(self) -> None:
        for filename in (
            "agent.py",
            "test_agent.py",
            "agent.ts",
            "agent.test.ts",
            "requirements.txt",
            "package-lock.json",
        ):
            path = f"examples/gemini-computer-use/{filename}"
            with self.subTest(path=path):
                self.assertTrue(ci.GROUPS["paired"] <= ci.scopes_for_path(path))
                self.assertEqual(ci.integration_examples_for_path(path), {"gemini-computer-use"})
        self.assertFalse(ci.integration_examples_for_path("examples/gemini-computer-use/README.md"))

    def test_selenium_native_inputs_route_to_existing_paired_jobs(self) -> None:
        with patch.dict(ci.INTEGRATION_EXAMPLES, {"selenium": "selenium-root"}):
            for filename in (
                "bridge.py",
                "install_driver.py",
                "test_bridge.py",
                "test_selenium.py",
                "requirements.txt",
                "package-lock.json",
                "test/selenium.live.test.ts",
            ):
                path = f"examples/selenium/{filename}"
                with self.subTest(path=path):
                    self.assertTrue(ci.GROUPS["paired"] <= ci.scopes_for_path(path))
                    self.assertEqual(ci.integration_examples_for_path(path), {"selenium"})
            self.assertFalse(ci.integration_examples_for_path("examples/selenium/README.md"))

    def test_shared_native_harness_inputs_cover_every_registered_project(self) -> None:
        for path in (*ci.INTEGRATION_INPUTS, ".github/workflows/paired-sdk-examples.yml"):
            with self.subTest(path=path):
                self.assertEqual(ci.integration_examples_for_path(path), set(ci.INTEGRATION_EXAMPLES))
                self.assertTrue(ci.GROUPS["paired"] <= ci.scopes_for_path(path))

    def test_offline_generator_and_its_tests_use_the_lightweight_suite(self) -> None:
        for path in ("docs/src/scripts/generate_llms.py", "tests/test_generate_llms_offline.py"):
            with self.subTest(path=path):
                selected = ci.scopes_for_path(path)
                self.assertIn("python_docs", selected)
                self.assertNotIn("python_unit", selected)
                self.assertFalse({name for name in selected if name.endswith("_live")})
        # Unfamiliar executable docs may also have regression tests outside tests/docs.
        self.assertIn("python_unit", ci.scopes_for_path("docs/src/scripts/new_generator.py"))

    def test_generated_reference_code_changes_only_need_offline_checks(self) -> None:
        for directory in ("sdk-reference", "typescript-sdk-reference", "cli-reference", "api-reference"):
            with self.subTest(directory=directory):
                selected = ci.scopes_for_path(f"docs/src/{directory}/session.mdx", code_changed=True)
                self.assertIn("docs_static", selected)
                self.assertFalse({name for name in selected if name.endswith("_live")})

    def test_policy_and_unknown_paths_select_broad_coverage(self) -> None:
        for path in (
            "scripts/ci_scope.py",
            "tests/scripts/test_ci_scope.py",
            "tests/scripts/test_ci_scope_offline.py",
            ".github/actions/ci-scope/action.yml",
            ".github/actions/wait-for-api/wait-for-api.sh",
            "new-runtime/config.json",
            "Makefile",
            ".github/workflows/new-test-workflow.yml",
            ".github/workflows/unknown-integration.yml",
        ):
            with self.subTest(path=path):
                self.assertEqual(ci.scopes_for_path(path), ci.ALL)
        for workflow, family in ci.WORKFLOWS.items():
            with self.subTest(workflow=workflow):
                self.assertEqual(ci.scopes_for_path(f".github/workflows/{workflow}"), ci.GROUPS[family])

    def test_provider_matrix_routes_library_schema_and_fixture_inputs(self) -> None:
        for path in (
            "packages/notte-llm/src/notte_llm/engine.py",
            "packages/notte-llm/src/notte_llm/prompts/extract-json-schema/multi-entity/system.md",
            "packages/notte-core/src/notte_core/schema.py",
            "packages/notte-core/src/notte_core/extraction.py",
            "packages/notte-core/src/notte_core/pruning.py",
            "packages/notte-core/src/notte_core/data.py",
            "tests/llm/test_provider_matrix.py",
            "tests/llm/provider_matrix.py",
            "tests/golden/snapshots/github_signin/scrape.md",
            "tests/golden/snapshots/duckduckgo/scrape.md",
            "tests/golden/snapshots/checkout/article/scrape.md",
            ".github/scripts/configure_llm.py",
            "scripts/llm_matrix_report.py",
            "tests/conftest.py",
        ):
            with self.subTest(path=path):
                self.assertIn("llm_provider_live", ci.scopes_for_path(path))
        self.assertNotIn("llm_provider_live", ci.scopes_for_path("node-sdk/src/client.ts"))
        self.assertNotIn("llm_provider_live", ci.scopes_for_path("packages/notte-browser/src/notte_browser/files.py"))
        self.assertTrue(ci.select("schedule", "", "")["llm_provider_live"])

    def test_act_benchmark_runs_only_its_offline_tests(self) -> None:
        for path in (
            "scripts/bench_act/bench.py",
            "scripts/bench_act/tasks/real.py",
            "scripts/bench_act/fixtures/a.html",
        ):
            with self.subTest(path=path):
                self.assertEqual(ci.scopes_for_path(path), {"python_static", "python_unit"})

    def test_periodic_and_manual_coverage(self) -> None:
        scheduled = ci.select("schedule", "", "")
        self.assertTrue(scheduled["python_live"])
        self.assertFalse(scheduled["python_unit"])
        self.assertFalse(scheduled["cli_contract"])
        self.assertTrue(all(scheduled[name] for name in ci.GROUPS["node"]))
        manual = ci.select("workflow_dispatch", "", "")
        self.assertTrue(all(manual[name] for name in ci.ALL))
        # Reviewed pushes retain every suite even when a valid comparison exists.
        reviewed = ci.select("reviewed_push", "a" * 40, "b" * 40)
        self.assertTrue(reviewed["full"])
        self.assertTrue(all(reviewed[name] for name in ci.ALL))

    def test_fences_preserve_language_options_code_and_unclosed_blocks(self) -> None:
        original = 'Prose\n```python title="demo"\nx = 1\n```\nMore prose\n'
        self.assertEqual(ci.fenced_code(original), ci.fenced_code("New prose\n" + original))
        for candidate in (original.replace("x = 1", "x = 2"), original.replace("python", "bash"), "```python\nx = 1"):
            with self.subTest(candidate=candidate):
                self.assertNotEqual(ci.fenced_code(original), ci.fenced_code(candidate))
        self.assertTrue(ci.fenced_code("~~~python\nx = 1\n~~~\n"))


class RegistrationRoutingTests(unittest.TestCase):
    def test_routing_contracts_accept_every_prepared_registration(self) -> None:
        fixtures = json.loads((ROOT / "tests/scripts/fixtures/integration_example_commands.json").read_text())
        for name, convention in fixtures["active"].items():
            self.assertEqual(ci.INTEGRATION_EXAMPLES.get(name), convention)
        augmented = {**ci.INTEGRATION_EXAMPLES, **fixtures["future"]}
        for registry in (ci.INTEGRATION_EXAMPLES, augmented):
            with self.subTest(registrations=len(registry)), patch.object(ci, "INTEGRATION_EXAMPLES", registry):
                result = unittest.TestResult()
                unittest.TestLoader().loadTestsFromTestCase(RoutingTests).run(result)
                self.assertGreater(result.testsRun, 0)
                self.assertFalse(result.errors, result.errors)
                self.assertFalse(result.failures, result.failures)
                owners = {"openai-agents", "claude-agents"}
                if "mongodb" in registry:
                    owners.add("mongodb")
                for path in ("docs/package.json", "docs/package-lock.json"):
                    self.assertEqual(ci.integration_examples_for_path(path), owners)


class GitHistoryTests(unittest.TestCase):
    def test_future_registrations_need_no_global_policy_or_runner_edits(self) -> None:
        fixtures = json.loads((ROOT / "tests/scripts/fixtures/integration_example_commands.json").read_text())
        current = fixtures["active"]
        registry_path = "scripts/integration_examples.json"
        for name, convention in fixtures["future"].items():
            with self.subTest(name=name):
                before = self.commit({registry_path: json.dumps(current)})
                registered = {**current, name: convention}
                head = self.commit({registry_path: json.dumps(registered)})
                with patch.object(ci, "INTEGRATION_EXAMPLES", registered):
                    registration = self.scope("push", before, head)
                    self.assertEqual(registration["integration_examples"], [name])
                    self.assertTrue(registration["paired_live"])
                    self.assertFalse(registration["paired_snippets_live"])
                    self.assertEqual(registration["paired_shards"], ["1/1"])
                    self.assertFalse(registration["python_live"])
                    self.assertFalse(registration["node_live"])
                    if name == "terraform-profiles":
                        path = "integrations/terraform-provider-notte/provider.go"
                    elif name == "mongodb":
                        path = "node-sdk/test/mongodb.integration.test.ts"
                    elif convention == "node-project":
                        path = f"examples/{name}/package.json"
                    elif convention == "valtown-deno":
                        path = f"examples/{name}/main.ts"
                    elif name in {"box", "yutori"}:
                        path = f"examples/{name}/requirements.txt"
                    else:
                        path = f"examples/{name}/pyproject.toml"
                    changed = self.commit({path: "synthetic native input\n"})
                    native = self.scope("push", head, changed)
                    self.assertEqual(native["integration_examples"], [name])
                    self.assertTrue(native["paired_live"])
                    self.assertFalse(native["full"])
                    self.assertFalse(all(native[family] for family in ci.ALL))

    def test_adaptive_cli_matrix_partitions_39_native_profiles_without_empty_owners(self) -> None:
        registry = {f"profile-{index:02}": "NOTTE_FIXTURE_PYTHON" for index in range(39)}
        before = self.commit({"scripts/integration_examples.json": "{}\n"})
        head = self.commit({"scripts/integration_examples.json": json.dumps(registry)})
        script = self.repo / "scripts/ci_scope.py"
        script.write_text((ROOT / "scripts/ci_scope.py").read_text())
        output = subprocess.check_output(
            [sys.executable, str(script), "--event", "push", "--base", before, "--head", head],
            cwd=self.repo,
            text=True,
        )
        scope = json.loads(output)
        self.assertTrue(scope["paired_live"])
        self.assertFalse(scope["paired_snippets_live"])
        with patch.object(runner, "REGISTRY", self.repo / "scripts/integration_examples.json"):
            with patch.dict(os.environ, {"INTEGRATION_EXAMPLES": json.dumps(scope["integration_examples"])}):
                assignments = [runner.projects(shard) for shard in scope["paired_shards"]]
        self.assertEqual(len(assignments), 20)
        self.assertTrue(all(1 <= len(group) <= 2 for group in assignments))
        self.assertEqual(sorted(name for group in assignments for name, _ in group), sorted(registry))

    def test_native_only_uses_one_owner_but_snippets_keep_two(self) -> None:
        before = self.commit({"scripts/integration_examples.json": "{}\n"})
        head = self.commit({"scripts/integration_examples.json": '{"openai-computer-use":"NOTTE_COMPUTER_USE_PYTHON"}'})
        scope = self.scope("push", before, head)
        self.assertTrue(scope["paired_live"])
        self.assertEqual(scope["paired_shards"], ["1/1"])
        snippet = self.commit({"docs/src/testers/sessions/example.ts": "export const example = true;\n"})
        scope = self.scope("push", head, snippet)
        self.assertTrue(scope["paired_snippets_live"])
        self.assertEqual(scope["paired_shards"], ["1/2", "2/2"])

    def test_zero_native_and_prose_diffs_do_not_start_adaptive_live_jobs(self) -> None:
        for head in (self.base, self.commit({"docs/src/pricing.mdx": "Updated pricing prose\n"})):
            with self.subTest(head=head):
                scope = self.scope("push", self.base, head)
                self.assertFalse(scope["paired_live"])
                self.assertEqual(scope["integration_examples"], [])
                self.assertEqual(scope["paired_shards"], ["1/1"])

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.repo = Path(self.directory.name)
        self.git_local_vars = set(
            subprocess.check_output(["git", "rev-parse", "--local-env-vars"]).decode().splitlines()
        )
        self.git("init", "-q")
        self.git("config", "commit.gpgsign", "false")
        self.git("config", "core.hooksPath", "/dev/null")
        # Detached housekeeping must not race strict temporary-directory cleanup.
        self.git("config", "maintenance.auto", "false")
        self.git("config", "gc.auto", "0")
        self.git("config", "user.name", "CI test")
        self.git("config", "user.email", "ci@example.invalid")
        self.base = self.commit({"README.md": "Original prose\n```python\nx = 1\n```\n"})

    def test_temporary_history_does_not_launch_automatic_git_maintenance(self) -> None:
        config = self.repo / ".git" / "inherited.config"
        config.write_text(
            "[maintenance]\n\tauto = true\n\tautoDetach = false\n[gc]\n\tauto = 1\n\tautoDetach = false\n"
        )
        commands: list[list[list[str]]] = []
        for index in range(2):
            if index:
                # A foreground positive control proves Git would otherwise
                # launch maintenance, without leaving another background task.
                self.git("config", "maintenance.auto", "true")
            trace = self.repo / ".git" / f"maintenance-{index}.jsonl"
            with patch.dict(
                os.environ,
                {"GIT_CONFIG_GLOBAL": str(config), "GIT_CONFIG_NOSYSTEM": "1", "GIT_TRACE2_EVENT": str(trace)},
            ):
                self.commit({"fixture.txt": str(index)})
            events = [json.loads(line) for line in trace.read_text().splitlines()]
            commands.append(
                [
                    event["argv"]
                    for event in events
                    if event.get("event") == "child_start"
                    and any(name in event.get("argv", []) for name in ("maintenance", "gc"))
                ]
            )
        self.assertEqual(commands[0], [])
        self.assertTrue(commands[1], "The control must exercise automatic Git maintenance")

    def git(self, *args: str) -> str:
        environment = {name: value for name, value in os.environ.items() if name not in self.git_local_vars}
        return (
            subprocess.check_output(["git", "-C", str(self.repo), *args], stderr=subprocess.PIPE, env=environment)
            .decode()
            .strip()
        )

    def test_temporary_history_ignores_callers_repository_variables(self) -> None:
        before = (self.repo / ".git/config").read_bytes()
        with patch.dict(
            os.environ,
            {
                "GIT_DIR": str(self.repo / ".git"),
                "GIT_WORK_TREE": str(self.repo),
                "GIT_COMMON_DIR": str(self.repo / ".git"),
                "GIT_INDEX_FILE": str(self.repo / ".git/index"),
                "GIT_OBJECT_DIRECTORY": str(self.repo / ".git/objects"),
            },
        ):
            fixture = type(self)("test_temporary_history_ignores_callers_repository_variables")
            try:
                fixture.setUp()
                self.assertEqual(Path(fixture.git("rev-parse", "--show-toplevel")).resolve(), fixture.repo.resolve())
                self.assertEqual(fixture.git("config", "--local", "maintenance.auto"), "false")
                self.assertFalse(fixture.scope("push", fixture.base, fixture.base)["full"])
            finally:
                fixture.doCleanups()
        self.assertEqual((self.repo / ".git/config").read_bytes(), before)

    def commit(self, files: dict[str, str]) -> str:
        for name, content in files.items():
            target = self.repo / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
        self.git("add", "-A")
        self.git("commit", "-qm", "Test change")
        return self.git("rev-parse", "HEAD")

    def scope(self, event: str, base: str, head: str) -> dict[str, bool | str | list[str] | list[dict[str, str]]]:
        original_git = ci.git
        environment = {name: value for name, value in os.environ.items() if name not in self.git_local_vars}
        with (
            patch.dict(os.environ, environment, clear=True),
            patch.object(ci, "git", side_effect=lambda *args: original_git("-C", str(self.repo), *args)),
        ):
            return ci.select(event, base, head)

    def workspace_files(self, version: str) -> dict[str, str]:
        files: dict[str, str] = {}
        lock = 'version = 1\nrevision = 5\nrequires-python = ">=3.11"\n'
        for name, directory in (
            ("notte", "."),
            ("notte-browser", "packages/notte-browser"),
            ("notte-core", "packages/notte-core"),
            ("notte-llm", "packages/notte-llm"),
            ("notte-sdk", "packages/notte-sdk"),
        ):
            dependency = f'"notte-core=={version}", ' if name != "notte-core" else ""
            files[str(Path(directory) / "pyproject.toml")] = (
                f'[project]\nname = "{name}"\nversion = "{version}"\n'
                f'dependencies = [{dependency}"external==1.0.0.dev0"]\n'
                'requires-python = ">=3.11"\n'
                "[project.optional-dependencies]\n"
                f'playwright = ["notte_sdk[playwright]=={version}"]\n'
                '[build-system]\nrequires = ["hatchling"]\n'
                "[tool.ruff]\nline-length = 120\n"
            )
            lock += f'\n[[package]]\nname = "{name}"\nversion = "{version}"\nsource = {{ editable = "{directory}" }}\n'
        files["pyproject.toml"] += '[tool.uv.workspace]\nmembers = ["packages/*", "."]\n'
        lock += (
            '\n[[package]]\nname = "external"\nversion = "1.0.0.dev0"\n'
            'source = { registry = "https://pypi.org/simple" }\n'
            'sdist = { url = "https://example.invalid/external.tar.gz", hash = "sha256:original" }\n'
        )
        files["uv.lock"] = lock
        return files

    def test_verified_workspace_version_bumps_keep_only_offline_checks(self) -> None:
        before = self.commit(self.workspace_files("1.0.0.dev0"))
        head = self.commit(self.workspace_files("1.0.1.dev0"))
        for event in ("push", "pull_request"):
            with self.subTest(event=event):
                scope = self.scope(event, before, head)
                self.assertEqual({name for name in ci.ALL if scope[name]}, {"python_static", "python_unit"})
                self.assertTrue(scope["file_checks"])
                self.assertTrue(scope["lint_all"])
                self.assertFalse(scope["full"])
                self.assertFalse(scope["paired_snippets_live"])
                self.assertEqual(scope["integration_examples"], [])

    def test_manifest_changes_beyond_workspace_versions_retain_live_coverage(self) -> None:
        mutations = (
            ("pyproject.toml", "external==1.0.0.dev0", "external==1.0.1.dev0"),
            ("pyproject.toml", 'requires-python = ">=3.11"', 'requires-python = ">=3.12"'),
            ("pyproject.toml", 'requires = ["hatchling"]', 'requires = ["setuptools"]'),
            ("pyproject.toml", "line-length = 120", "line-length = 100"),
            ("pyproject.toml", "line-length = 120", "line-length = 120.0"),
            ("pyproject.toml", 'members = ["packages/*", "."]', 'members = ["packages/*", ".", "new"]'),
            ("pyproject.toml", "notte-core==1.0.1.dev0", "notte-core>=1.0.1.dev0"),
            ("pyproject.toml", "notte-core==1.0.1.dev0", "notte-core==1.0.0.dev0"),
            ("pyproject.toml", "notte_sdk[playwright]", "notte_sdk[other]"),
            ("pyproject.toml", "notte_sdk[playwright]==1.0.1.dev0", "notte_sdk[playwright]==1.0.1.dev0; extra == 'x'"),
            ("packages/notte-sdk/pyproject.toml", 'name = "notte-sdk"', 'name = "renamed-sdk"'),
            ("packages/notte-sdk/pyproject.toml", 'version = "1.0.1.dev0"', 'version = "1.0.0.dev0"'),
        )
        for path, original, replacement in mutations:
            with self.subTest(path=path, replacement=replacement):
                before = self.commit(self.workspace_files("1.0.0.dev0"))
                changed = self.workspace_files("1.0.1.dev0")
                self.assertIn(original, changed[path])
                changed[path] = changed[path].replace(original, replacement)
                head = self.commit(changed)
                scope = self.scope("push", before, head)
                self.assertTrue(scope["python_live"])
                self.assertTrue(scope["llm_provider_live"])
                self.assertTrue(scope["paired_live"])
                self.assertEqual(scope["integration_examples"], sorted(ci.integration_examples_for_path("uv.lock")))

    def test_lock_changes_beyond_workspace_versions_retain_live_coverage(self) -> None:
        mutations = (
            ("revision = 5", "revision = 6"),
            ("version = 1\nrevision", "version = true\nrevision"),
            ('requires-python = ">=3.11"', 'requires-python = ">=3.12"'),
            ('name = "external"\nversion = "1.0.0.dev0"', 'name = "external"\nversion = "1.0.1.dev0"'),
            ("sha256:original", "sha256:changed"),
            ("https://pypi.org/simple", "https://other.invalid/simple"),
            ('editable = "packages/notte-sdk"', 'editable = "other/sdk"'),
            ('name = "notte-sdk"\nversion = "1.0.1.dev0"', 'name = "notte-sdk"\nversion = "1.0.0.dev0"'),
            ('name = "notte-sdk"', 'name = "missing-sdk"'),
            ('name = "notte-sdk"', 'name = "notte-core"'),
        )
        for original, replacement in mutations:
            with self.subTest(replacement=replacement):
                before = self.commit(self.workspace_files("1.0.0.dev0"))
                changed = self.workspace_files("1.0.1.dev0")
                self.assertIn(original, changed["uv.lock"])
                changed["uv.lock"] = changed["uv.lock"].replace(original, replacement)
                head = self.commit(changed)
                self.assertTrue(self.scope("push", before, head)["python_live"])

    def test_unreadable_version_inputs_retain_normal_coverage(self) -> None:
        for path in ("pyproject.toml", "packages/notte-sdk/pyproject.toml", "uv.lock"):
            with self.subTest(path=path):
                before = self.commit(self.workspace_files("1.0.0.dev0"))
                changed = self.workspace_files("1.0.1.dev0")
                changed[path] = "[broken TOML\n"
                head = self.commit(changed)
                self.assertTrue(self.scope("push", before, head)["python_live"])

    def test_deleted_symlinked_or_executable_version_inputs_are_not_exempt(self) -> None:
        path = "packages/notte-sdk/pyproject.toml"
        for mode in ("deleted", "symlink", "executable"):
            with self.subTest(mode=mode):
                target = self.repo / path
                if target.is_symlink():
                    target.unlink()
                before = self.commit(self.workspace_files("1.0.0.dev0"))
                changed = self.workspace_files("1.0.1.dev0")
                if mode in {"deleted", "symlink"}:
                    del changed[path]
                    target.unlink()
                    if mode == "symlink":
                        target.symlink_to("../../pyproject.toml")
                else:
                    target.chmod(0o755)
                head = self.commit(changed)
                self.assertTrue(self.scope("push", before, head)["python_live"])

    def test_version_bumps_do_not_suppress_other_changes_or_earlier_commits(self) -> None:
        for path in ("packages/notte-sdk/src/notte_sdk/client.py", "scripts/new_tool.py", "docs/src/images/logo.svg"):
            with self.subTest(path=path):
                before = self.commit(self.workspace_files("1.0.0.dev0"))
                self.commit({path: "original content\n"})
                head = self.commit(self.workspace_files("1.0.1.dev0"))
                self.assertTrue(self.scope("push", before, head)["python_live"])
                self.assertTrue(self.scope("pull_request", before, head)["python_live"])

    def test_version_only_pr_uses_its_merge_base(self) -> None:
        before = self.commit(self.workspace_files("1.0.0.dev0"))
        branch = self.git("branch", "--show-current")
        self.git("checkout", "-qb", "version")
        feature = self.commit(self.workspace_files("1.0.1.dev0"))
        self.git("checkout", branch)
        main = self.commit({"packages/notte-sdk/src/notte_sdk/client.py": "runtime = True\n"})
        scope = self.scope("pull_request", main, feature)
        self.assertEqual(scope["base"], before)
        self.assertFalse(scope["python_live"])
        self.assertTrue(scope["python_unit"])

    def test_complete_diff_unions_native_projects_and_skips_prose(self) -> None:
        prose = self.commit({"examples/openai-computer-use/README.md": "New instructions\n"})
        self.assertEqual(self.scope("push", self.base, prose)["integration_examples"], [])
        self.commit({"examples/openai-computer-use/python/demo.py": "runtime = True\n"})
        head = self.commit({"docs/src/pricing.mdx": "More prose\n"})
        scope = self.scope("push", self.base, head)
        self.assertEqual(scope["integration_examples"], ["openai-computer-use"])
        self.assertTrue(scope["paired_static"] and scope["paired_live"])
        self.assertFalse(scope["paired_snippets_live"])
        self.assertEqual(ci.select("push", "", "")["integration_examples"], sorted(ci.INTEGRATION_EXAMPLES))

    def test_native_runner_diff_skips_snippets_but_sdk_changes_keep_both(self) -> None:
        head = self.commit({"scripts/ci_integration_examples.py": "runner = True\n"})
        scope = self.scope("push", self.base, head)
        self.assertEqual(scope["integration_examples"], sorted(ci.INTEGRATION_EXAMPLES))
        self.assertTrue(scope["paired_static"] and scope["paired_live"])
        self.assertFalse(scope["paired_snippets_live"])
        shared = self.commit({"packages/notte-sdk/src/notte_sdk/client.py": "client = True\n"})
        scope = self.scope("push", head, shared)
        self.assertEqual(scope["integration_examples"], sorted(ci.integration_examples_for_path("uv.lock")))
        self.assertTrue(scope["paired_snippets_live"])
        recipe = self.commit({".github/workflows/selector-repair.yml": "recipe = True\n"})
        scope = self.scope("push", shared, recipe)
        self.assertEqual(scope["integration_examples"], ["github-actions"])
        self.assertTrue(scope["paired_static"] and scope["paired_live"])
        self.assertFalse(scope["paired_snippets_live"])
        self.assertEqual(scope["paired_shards"], ["1/1"])

    def test_pull_requests_and_pushes_select_the_same_native_consumers(self) -> None:
        sdk = self.commit({"packages/notte-sdk/src/notte_sdk/client.py": "client = True\n", "uv.lock": "lock = 1\n"})
        for event in ("push", "pull_request"):
            scope = self.scope(event, self.base, sdk)
            self.assertEqual(scope["integration_examples"], sorted(ci.integration_examples_for_path("uv.lock")))
            self.assertTrue(scope["paired_live"] and scope["paired_snippets_live"])
        unknown = self.commit({"scripts/new_tool.py": "tool = True\n"})
        for event in ("push", "pull_request"):
            self.assertEqual(self.scope(event, sdk, unknown)["integration_examples"], sorted(ci.INTEGRATION_EXAMPLES))
        project = self.commit({"examples/temporal/src/workflow.ts": "workflow = True\n"})
        self.assertEqual(self.scope("pull_request", unknown, project)["integration_examples"], ["temporal"])
        runner = self.commit({"scripts/ci_integration_examples.py": "runner = True\n"})
        self.assertEqual(
            self.scope("pull_request", project, runner)["integration_examples"], sorted(ci.INTEGRATION_EXAMPLES)
        )

    def test_snippet_changes_do_not_repeat_unrelated_native_projects(self) -> None:
        head = self.commit({"docs/src/testers/sessions/index.py": "snippet = True\n"})
        scope = self.scope("push", self.base, head)
        self.assertTrue(scope["paired_live"] and scope["paired_snippets_live"])
        self.assertEqual(scope["integration_examples"], [])

    def test_registry_append_runs_only_the_added_native_project(self) -> None:
        path = "scripts/integration_examples.json"
        old = {"openai-computer-use": "NOTTE_COMPUTER_USE_PYTHON"}
        base = self.commit({path: json.dumps(old)})
        head = self.commit({path: json.dumps({**old, "anthropic-computer-use": "NOTTE_COMPUTER_USE_PYTHON"})})
        for event in ("push", "pull_request"):
            scope = self.scope(event, base, head)
            self.assertEqual(scope["integration_examples"], ["anthropic-computer-use"])
            self.assertTrue(scope["paired_static"] and scope["paired_live"])
            self.assertFalse(scope["paired_snippets_live"])

    def test_registry_entry_change_skips_unchanged_native_projects(self) -> None:
        path = "scripts/integration_examples.json"
        base = self.commit({path: json.dumps(ci.INTEGRATION_EXAMPLES)})
        changed = {**ci.INTEGRATION_EXAMPLES, "openai-computer-use": "NOTTE_NEW_COMPUTER_USE_PYTHON"}
        head = self.commit({path: json.dumps(changed)})
        scope = self.scope("push", base, head)
        self.assertEqual(scope["integration_examples"], ["openai-computer-use"])
        self.assertFalse(scope["paired_snippets_live"])
        runner = self.commit({"scripts/ci_integration_examples.py": "updated_runner = True\n"})
        self.assertEqual(self.scope("push", head, runner)["integration_examples"], sorted(ci.INTEGRATION_EXAMPLES))

    def test_registry_append_preserves_opaque_native_conventions(self) -> None:
        path = "scripts/integration_examples.json"
        old = {"gemini-computer-use": "gemini-root", "selenium": "selenium-root"}
        base = self.commit({path: json.dumps(old)})
        head = self.commit({path: json.dumps({**old, "anthropic-computer-use": "NOTTE_COMPUTER_USE_PYTHON"})})
        scope = self.scope("push", base, head)
        self.assertEqual(scope["integration_examples"], ["anthropic-computer-use"])
        self.assertTrue(scope["paired_static"] and scope["paired_live"])
        self.assertFalse(scope["paired_snippets_live"])

    def test_registry_removal_and_formatting_keep_static_without_live(self) -> None:
        path = "scripts/integration_examples.json"
        base = self.commit({path: json.dumps(ci.INTEGRATION_EXAMPLES)})
        removed = self.commit({path: "{}"})
        formatted = self.commit({path: "{\n}\n"})
        for before, after in ((base, removed), (removed, formatted)):
            scope = self.scope("push", before, after)
            self.assertEqual(scope["integration_examples"], [])
            self.assertTrue(scope["paired_static"])
            self.assertFalse(scope["paired_live"] or scope["paired_snippets_live"])

    def test_unavailable_or_malformed_registry_history_falls_back_to_all(self) -> None:
        path = "scripts/integration_examples.json"
        previous = self.base  # The registry is missing from the initial commit.
        valid = '{"openai-computer-use": "NOTTE_COMPUTER_USE_PYTHON"}'
        for content in (
            valid,
            "[]",
            '{"openai-computer-use": 1}',
            '{"../escape": "NOTTE_COMPUTER_USE_PYTHON"}',
            "{",
            valid,
        ):
            head = self.commit({path: content})
            scope = self.scope("push", previous, head)
            self.assertEqual(scope["integration_examples"], sorted(ci.INTEGRATION_EXAMPLES))
            self.assertTrue(scope["paired_static"] and scope["paired_live"])
            previous = head

    def test_push_includes_every_commit_and_unions_scopes(self) -> None:
        self.commit({"packages/notte-sdk/src/client.py": "runtime = True\n"})
        head = self.commit({"docs/src/pricing.mdx": "New pricing prose\n"})
        scope = self.scope("push", self.base, head)
        self.assertTrue(scope["python_live"])
        self.assertTrue(scope["python_docs"])
        self.assertFalse(scope["node_generated"])
        self.assertFalse(scope["full"])

    def test_standalone_integration_diff_keeps_offline_checks_and_registered_paired_owner(self) -> None:
        head = self.commit(
            {
                ".github/workflows/braintrust-integration.yml": "name: Braintrust integration\n",
                "examples/braintrust/python/demo.py": "browser_task = True\n",
                "examples/braintrust/typescript/src/demo.ts": "export const browserTask = true;\n",
                "examples/braintrust/uv.lock": "version = 1\n",
                "docs/src/integrations/braintrust.mdx": "Trace browser tasks with the linked examples.\n",
                "docs/src/integrations/index.mdx": "Browse integrations.\n",
                "docs/src/docs.json": "{}\n",
                "docs/src/llms.txt": "Braintrust guide\n",
                "tests/scripts/test_ci_staging_scope.py": "# Validate workflow coordination\n",
            }
        )
        registries = (
            {name: convention for name, convention in ci.INTEGRATION_EXAMPLES.items() if name != "braintrust"},
            {**ci.INTEGRATION_EXAMPLES, "braintrust": "typescript-driver"},
        )
        for registry in registries:
            registered = "braintrust" in registry
            with self.subTest(registered=registered), patch.object(ci, "INTEGRATION_EXAMPLES", registry):
                scope = self.scope("pull_request", self.base, head)
                for name in ("python_static", "python_unit", "python_docs", "docs_static", "paired_static"):
                    self.assertTrue(scope[name], name)
                self.assertEqual(scope["integration_examples"], ["braintrust"] if registered else [])
                self.assertEqual(scope["paired_live"], registered)
                for name in ci.ALL:
                    if name.endswith("_live") and name != "paired_live":
                        self.assertFalse(scope[name], name)

        runtime = self.commit(
            {
                "packages/notte-sdk/src/notte_sdk/client.py": "runtime = True\n",
                "node-sdk/src/session.ts": "export const runtime = true;\n",
            }
        )
        scope = self.scope("pull_request", self.base, runtime)
        for name in ("python_live", "node_live", "paired_live", "readme_live"):
            self.assertTrue(scope[name], name)

    def test_docs_only_push_does_not_run_python_unit_live_or_cli(self) -> None:
        before = self.commit({"docs/src/pricing.mdx": "Price: 1\n"})
        head = self.commit({"docs/src/pricing.mdx": "Price: 2\n"})
        scope = self.scope("push", before, head)
        self.assertTrue(scope["docs_static"])
        self.assertTrue(scope["python_docs"])
        for name in ("python_unit", "python_live", "cli_contract", "docs_live", "paired_live", "node_live"):
            self.assertFalse(scope[name], name)

    def test_prose_edits_around_unchanged_readme_code_skip_live(self) -> None:
        head = self.commit({"README.md": "Revised prose\n```python\nx = 1\n```\n"})
        self.assertFalse(self.scope("push", self.base, head)["readme_live"])
        next_head = self.commit({"README.md": "Revised prose\n```python\nx = 2\n```\n"})
        self.assertTrue(self.scope("push", head, next_head)["readme_live"])

    def test_lint_configuration_checks_all_files_but_ordinary_edits_do_not(self) -> None:
        before = self.base
        for path in (".pre-commit-config.yaml", "pyproject.toml", "packages/notte-sdk/pyproject.toml"):
            with self.subTest(path=path):
                head = self.commit({path: "# Updated configuration\n"})
                self.assertTrue(self.scope("push", before, head)["lint_all"])
                before = head
        head = self.commit({"packages/notte-sdk/src/client.py": "runtime = True\n"})
        self.assertFalse(self.scope("push", before, head)["lint_all"])

    def test_deleting_or_renaming_runtime_to_docs_retains_runtime_coverage(self) -> None:
        before = self.commit({"packages/notte-sdk/src/old.py": "old = True\n"})
        (self.repo / "docs/src").mkdir(parents=True)
        self.git("mv", "packages/notte-sdk/src/old.py", "docs/src/old.mdx")
        self.git("commit", "-qm", "Rename runtime")
        head = self.git("rev-parse", "HEAD")
        self.assertTrue(self.scope("push", before, head)["python_live"])
        before_delete = self.commit({"packages/notte-sdk/src/new.py": "runtime = True\n"})
        (self.repo / "packages/notte-sdk/src/new.py").unlink()
        deletion = self.commit({"docs/src/page.mdx": "Prose\n"})
        self.assertTrue(self.scope("push", before_delete, deletion)["python_live"])

    def test_new_and_deleted_prose_pages_do_not_run_live_suites(self) -> None:
        head = self.commit({"docs/src/page.mdx": "New prose only\n"})
        self.assertFalse(self.scope("push", self.base, head)["docs_live"])
        (self.repo / "docs/src/page.mdx").unlink()
        deletion = self.commit({})
        scope = self.scope("push", head, deletion)
        self.assertFalse(scope["docs_live"])
        self.assertFalse(scope["lint_all"])
        self.assertTrue(scope["docs_links"])

    def test_doc_renames_keep_link_checks_without_duplicate_global_checks(self) -> None:
        before = self.commit({"docs/src/old.mdx": "Existing prose\n"})
        self.git("mv", "docs/src/old.mdx", "docs/src/new.mdx")
        head = self.commit({})
        scope = self.scope("push", before, head)
        self.assertFalse(scope["docs_links"])
        self.assertTrue(scope["python_static"])
        self.assertFalse(scope["docs_live"])

    def test_pr_uses_merge_base_excluding_main_only_runtime_changes(self) -> None:
        branch = self.git("branch", "--show-current")
        self.git("checkout", "-qb", "feature")
        feature = self.commit({"docs/src/page.mdx": "Prose\n"})
        self.git("checkout", branch)
        main = self.commit({"packages/notte-sdk/src/client.py": "runtime = True\n"})
        scope = self.scope("pull_request", main, feature)
        self.assertEqual(scope["base"], self.base)
        self.assertFalse(scope["python_live"])

    def test_missing_invalid_or_unavailable_comparisons_run_everything(self) -> None:
        for base in ("", "0" * 40, "f" * 40, "HEAD~1", "$(echo dangerous)"):
            with self.subTest(base=base), contextlib.redirect_stderr(io.StringIO()):
                scope = self.scope("push", base, self.base)
                self.assertTrue(scope["full"])
                self.assertTrue(all(scope[name] for name in ci.ALL))

    def test_path_with_newline_is_not_split_into_fake_paths(self) -> None:
        head = self.commit({"tests/browser/test_line\nnode-sdk/src/client.ts": "test = True\n"})
        scope = self.scope("push", self.base, head)
        self.assertFalse(scope["node_live"])
        self.assertTrue(scope["python_unit"])

    def test_cli_emits_single_json_output_and_suite_summary(self) -> None:
        output = self.repo / "outputs"
        summary = self.repo / "summary"
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/ci_scope.py"),
                "--event",
                "push",
                "--base",
                self.base,
                "--head",
                self.base,
                "--output",
                str(output),
                "--summary",
                str(summary),
            ],
            cwd=self.repo,
            capture_output=True,
            text=True,
            check=True,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        payload = json.loads(output.read_text().removeprefix("scope="))
        self.assertEqual(payload, json.loads(result.stdout))
        self.assertFalse(any(payload[name] for name in ci.ALL))
        self.assertFalse(payload["file_checks"])
        self.assertIn("Selected CI suites", summary.read_text())

    def test_non_python_files_keep_generic_file_checks(self) -> None:
        before = self.base
        for path in (
            "node-sdk/src/client.ts",
            "node-sdk/package.json",
            "node-sdk/README.md",
            ".github/workflows/node-sdk-ci.yml",
            ".github/workflows/docs-tests-cicd.yml",
            ".github/workflows/paired-sdk-examples.yml",
            ".github/workflows/readme-check.yml",
        ):
            with self.subTest(path=path):
                head = self.commit({path: "changed content\n"})
                scope = self.scope("push", before, head)
                self.assertTrue(scope["file_checks"])
                self.assertFalse(scope["python_static"])
                before = head

    def test_python_helpers_outside_packages_keep_python_lint(self) -> None:
        head = self.commit({"node-sdk/test/helpers/fixture.py": "fixture = True\n"})
        scope = self.scope("push", self.base, head)
        self.assertTrue(scope["file_checks"])
        self.assertTrue(scope["python_static"])

    def test_symlinked_readme_never_skips_execution(self) -> None:
        (self.repo / "README.md").unlink()
        (self.repo / "README.md").symlink_to("example.md")
        head = self.commit({"example.md": "```python\nx = 2\n```\n"})
        self.assertTrue(self.scope("push", self.base, head)["readme_live"])

    def test_git_timeout_selects_full_coverage(self) -> None:
        with patch.object(ci, "git", side_effect=subprocess.TimeoutExpired("git", 30)):
            with contextlib.redirect_stderr(io.StringIO()):
                scope = ci.select("push", self.base, self.base)
        self.assertTrue(scope["full"])
        self.assertTrue(all(scope[name] for name in ci.ALL))


if __name__ == "__main__":
    unittest.main()
