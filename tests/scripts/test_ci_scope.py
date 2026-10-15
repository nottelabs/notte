"""Offline routing contracts, including real Git history and CLI output."""

from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import ci_scope as ci

ROOT = Path(__file__).resolve().parents[2]


class RoutingTests(unittest.TestCase):
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
        self.assertEqual(ci.scopes_for_path("tests/integration/sdk/test_session.py"), {"python_static", "python_live"})
        self.assertEqual(ci.scopes_for_path("tests/docs/test_pricing_docs.py"), {"python_static", "python_docs"})
        for path in ("tests/conftest.py", "tests/data/cookies.json", "tests/mock/mock_service.py"):
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
            "packages/notte-core/src/notte_core/browser/observation.py",
            "packages/notte-core/src/notte_core/prompts/system.md",
            "packages/notte-browser/src/notte_browser/playwright.py",
            "packages/notte-agent/pyproject.toml",
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
            ".github/actions/ci-scope/action.yml",
            ".github/actions/wait-for-api/wait-for-api.sh",
            "new-runtime/config.json",
            "Makefile",
            ".github/workflows/new-test-workflow.yml",
        ):
            with self.subTest(path=path):
                self.assertEqual(ci.scopes_for_path(path), ci.ALL)
        for workflow, family in ci.WORKFLOWS.items():
            with self.subTest(workflow=workflow):
                self.assertEqual(ci.scopes_for_path(f".github/workflows/{workflow}"), ci.GROUPS[family])

    def test_periodic_and_manual_coverage(self) -> None:
        scheduled = ci.select("schedule", "", "")
        self.assertTrue(scheduled["python_live"])
        self.assertFalse(scheduled["python_unit"])
        self.assertFalse(scheduled["cli_contract"])
        self.assertTrue(all(scheduled[name] for name in ci.GROUPS["node"]))
        manual = ci.select("workflow_dispatch", "", "")
        self.assertTrue(all(manual[name] for name in ci.ALL))

    def test_fences_preserve_language_options_code_and_unclosed_blocks(self) -> None:
        original = 'Prose\n```python title="demo"\nx = 1\n```\nMore prose\n'
        self.assertEqual(ci.fenced_code(original), ci.fenced_code("New prose\n" + original))
        for candidate in (original.replace("x = 1", "x = 2"), original.replace("python", "bash"), "```python\nx = 1"):
            with self.subTest(candidate=candidate):
                self.assertNotEqual(ci.fenced_code(original), ci.fenced_code(candidate))
        self.assertTrue(ci.fenced_code("~~~python\nx = 1\n~~~\n"))


class GitHistoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.repo = Path(self.directory.name)
        self.git("init", "-q")
        self.git("config", "user.name", "CI test")
        self.git("config", "user.email", "ci@example.invalid")
        self.base = self.commit({"README.md": "Original prose\n```python\nx = 1\n```\n"})

    def git(self, *args: str) -> str:
        return subprocess.check_output(["git", "-C", str(self.repo), *args], stderr=subprocess.PIPE).decode().strip()

    def commit(self, files: dict[str, str]) -> str:
        for name, content in files.items():
            target = self.repo / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
        self.git("add", "-A")
        self.git("commit", "-qm", "Test change")
        return self.git("rev-parse", "HEAD")

    def scope(self, event: str, base: str, head: str) -> dict[str, bool | str]:
        original_git = ci.git
        with patch.object(ci, "git", side_effect=lambda *args: original_git("-C", str(self.repo), *args)):
            return ci.select(event, base, head)

    def test_push_includes_every_commit_and_unions_scopes(self) -> None:
        self.commit({"packages/notte-sdk/src/client.py": "runtime = True\n"})
        head = self.commit({"docs/src/pricing.mdx": "New pricing prose\n"})
        scope = self.scope("push", self.base, head)
        self.assertTrue(scope["python_live"])
        self.assertTrue(scope["python_docs"])
        self.assertFalse(scope["node_generated"])
        self.assertFalse(scope["full"])

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
