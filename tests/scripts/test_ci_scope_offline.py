"""Offline routing must retain coverage for runtime and unfamiliar inputs."""

from __future__ import annotations

import unittest

from scripts import ci_scope as ci
from tests.scripts import test_ci_scope as history


class OfflinePathRoutingTests(unittest.TestCase):
    def test_release_tools_select_python_offline_checks(self) -> None:
        for path in ("scripts/release_version.py", "scripts/build_release.py"):
            with self.subTest(path=path):
                self.assertEqual(ci.scopes_for_path(path), {"python_static", "python_unit"})
                self.assertEqual(ci.integration_examples_for_path(path), set())

    def test_openapi_tools_and_order_fixtures_keep_generation_checks(self) -> None:
        expected = {"python_static", "python_unit", "node_static", "node_generated"}
        for path in (
            "scripts/openapi_order.py",
            "scripts/openapi_contract.py",
            "scripts/generate_sdk_models.py",
            "scripts/generate_sdk_endpoints.py",
            "tests/data/openapi-order/base.json",
            "tests/data/openapi-order/nested/reordered.json",
        ):
            with self.subTest(path=path):
                self.assertEqual(ci.scopes_for_path(path), expected)
                self.assertEqual(ci.integration_examples_for_path(path), set())

    def test_presentation_assets_select_file_and_docs_assertions(self) -> None:
        for path in (
            "docs/src/images/overview.png",
            "docs/src/images/nested/overview.webp",
            "docs/src/logo/light.svg",
            "docs/src/fonts/inter.woff2",
            "docs/src/favicon.ico",
        ):
            with self.subTest(path=path):
                self.assertEqual(ci.scopes_for_path(path), {"python_static", "python_docs"})
                self.assertEqual(ci.integration_examples_for_path(path), set())

    def test_asset_extensions_do_not_exempt_execution_fixtures(self) -> None:
        for path, required in (
            ("docs/src/testers/fixture.svg", {"docs_live", "paired_live"}),
            ("docs/src/tests/fixture.png", {"docs_live"}),
            ("docs/src/sniptest/fixture.svg", {"paired_live"}),
        ):
            with self.subTest(path=path):
                self.assertTrue(required <= ci.scopes_for_path(path))

    def test_docs_configuration_and_executable_content_keep_coverage(self) -> None:
        for path in (
            "docs/src/images/config.json",
            "docs/src/fonts/loader.js",
            "docs/src/scripts/new_generator.py",
            "docs/src/conftest.py",
            "docs/package-lock.json",
        ):
            with self.subTest(path=path):
                selected = ci.scopes_for_path(path)
                self.assertIn("python_unit", selected)
                self.assertTrue({"docs_live", "paired_live"} <= selected)
        self.assertIn("docs_live", ci.scopes_for_path("docs/src/guides/example.mdx", code_changed=True))

    def test_unknown_scripts_and_schemas_keep_broad_coverage(self) -> None:
        for path in (
            "scripts/new_generator.py",
            "scripts/openapi_order_extra.py",
            "scripts/release_version.py.json",
            "openapi/new_snapshot.json",
        ):
            with self.subTest(path=path):
                self.assertEqual(ci.scopes_for_path(path), ci.ALL)
        for path in ("tests/data/cookies.json", "tests/data/openapi-ordering/base.json"):
            with self.subTest(path=path):
                self.assertTrue(ci.PYTHON_RUNTIME <= ci.scopes_for_path(path))

    def test_runtime_schemas_and_generated_outputs_keep_runtime_coverage(self) -> None:
        for path in (
            "packages/notte-core/src/notte_core/schema.py",
            "packages/notte-sdk/src/notte_sdk/_generated/models.py",
            "packages/notte-sdk/src/notte_sdk/_generated/schema_index.json",
        ):
            with self.subTest(path=path):
                self.assertTrue(ci.PYTHON_RUNTIME <= ci.scopes_for_path(path))
        for path in ("node-sdk/src/resources.gen.ts", "node-sdk/src/lib/client/types.gen.ts"):
            with self.subTest(path=path):
                self.assertTrue({"node_static", "node_generated", "node_live"} <= ci.scopes_for_path(path))


class OfflineGitHistoryTests(unittest.TestCase):
    def setUp(self) -> None:
        # Compose the existing fixture without inheriting its discovered tests.
        self.history = history.GitHistoryTests()
        self.history.setUp()
        self.addCleanup(self.history.doCleanups)

    def test_asset_only_change_keeps_file_checks_without_live_jobs(self) -> None:
        head = self.history.commit({"docs/src/images/overview.svg": "<svg/>\n"})
        for event in ("push", "pull_request"):
            with self.subTest(event=event):
                scope = self.history.scope(event, self.history.base, head)
                self.assertEqual({name for name in ci.ALL if scope[name]}, {"python_static", "python_docs"})
                self.assertTrue(scope["file_checks"])
                self.assertFalse(scope["full"])
                self.assertFalse(scope["lint_all"])
                self.assertFalse(scope["paired_snippets_live"])
                self.assertEqual(scope["integration_examples"], [])

    def test_offline_inputs_do_not_suppress_runtime_from_an_earlier_commit(self) -> None:
        self.history.commit({"packages/notte-sdk/src/notte_sdk/client.py": "runtime = True\n"})
        head = self.history.commit(
            {
                "scripts/release_version.py": "release = True\n",
                "tests/data/openapi-order/base.json": "{}\n",
                "docs/src/logo/light.svg": "<svg/>\n",
            }
        )
        for event in ("push", "pull_request"):
            with self.subTest(event=event):
                scope = self.history.scope(event, self.history.base, head)
                self.assertTrue(scope["python_unit"])
                self.assertTrue(scope["python_live"])
                self.assertTrue(scope["node_generated"])
                self.assertTrue(scope["paired_live"])
                self.assertTrue(scope["python_docs"])

    def test_offline_inputs_do_not_suppress_an_unknown_file_in_the_same_commit(self) -> None:
        head = self.history.commit({"scripts/build_release.py": "release = True\n", "new-runtime/config.json": "{}\n"})
        scope = self.history.scope("push", self.history.base, head)
        self.assertTrue(all(scope[name] for name in ci.ALL))
        self.assertEqual(scope["integration_examples"], sorted(ci.INTEGRATION_EXAMPLES))

    def test_renaming_runtime_to_an_asset_retains_the_deleted_runtime_path(self) -> None:
        before = self.history.commit({"packages/notte-sdk/src/notte_sdk/old.py": "runtime = True\n"})
        (self.history.repo / "docs/src/images").mkdir(parents=True)
        self.history.git("mv", "packages/notte-sdk/src/notte_sdk/old.py", "docs/src/images/old.svg")
        head = self.history.commit({})
        scope = self.history.scope("push", before, head)
        self.assertTrue(scope["python_live"])
        self.assertTrue(scope["paired_live"])
        self.assertTrue(scope["python_docs"])

    def test_renaming_offline_tool_to_unknown_script_retains_broad_coverage(self) -> None:
        before = self.history.commit({"scripts/openapi_order.py": "order = True\n"})
        self.history.git("mv", "scripts/openapi_order.py", "scripts/new_generator.py")
        head = self.history.commit({})
        scope = self.history.scope("push", before, head)
        self.assertTrue(all(scope[name] for name in ci.ALL))

    def test_deleted_asset_keeps_documentation_link_validation(self) -> None:
        before = self.history.commit({"docs/src/images/overview.svg": "<svg/>\n"})
        (self.history.repo / "docs/src/images/overview.svg").unlink()
        head = self.history.commit({})
        scope = self.history.scope("push", before, head)
        self.assertEqual({name for name in ci.ALL if scope[name]}, {"python_static", "python_docs"})
        self.assertTrue(scope["file_checks"])
        self.assertTrue(scope["docs_links"])

    def test_deleted_openapi_fixture_keeps_generation_validation(self) -> None:
        before = self.history.commit({"tests/data/openapi-order/base.json": "{}\n"})
        (self.history.repo / "tests/data/openapi-order/base.json").unlink()
        head = self.history.commit({})
        scope = self.history.scope("push", before, head)
        self.assertEqual(
            {name for name in ci.ALL if scope[name]},
            {"python_static", "python_unit", "node_static", "node_generated"},
        )
        self.assertTrue(scope["file_checks"])


if __name__ == "__main__":
    unittest.main()
