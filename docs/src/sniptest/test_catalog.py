"""No snippet, including manual groups and commands, may bypass source generation."""

import ast
import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import generate
from catalog import catalog_sources, check_catalog_migration, load_catalog, source_path


class RepositoryCatalogTest(unittest.TestCase):
    def test_session_quickstart_tabs_do_the_same_task(self):
        python = ast.parse((generate.TESTERS_DIR / "quickstart/cdp_session.py").read_text())
        typescript = (generate.TESTERS_DIR / "quickstart/cdp_session.ts").read_text()
        navigation = [
            node.args[0].value
            for node in ast.walk(python)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "goto"
            and isinstance(node.args[0], ast.Constant)
        ]
        screenshots = [
            [item.value for item in ast.walk(keyword.value) if isinstance(item, ast.Constant)][-1]
            for node in ast.walk(python)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "screenshot"
            for keyword in node.keywords
            if keyword.arg == "path"
        ]
        self.assertEqual(navigation, re.findall(r"page\.goto\(['\"]([^'\"]+)", typescript))
        self.assertEqual(screenshots, re.findall(r"page\.screenshot\(\{ path: .*?['\"]([^'\"]+)", typescript))
        self.assertEqual(len(navigation), 1)
        self.assertEqual(len(screenshots), 1)

    def test_all_snippets_have_sources_and_are_current(self):
        expected = generate.get_all_generated_snippets()
        self.assertEqual(set(generate.SNIPPETS_DIR.rglob("*.mdx")), expected)
        for source in generate.get_all_tester_files():
            with self.subTest(source=source):
                self.assertEqual(generate.get_output_path(source).read_text(), generate.render_file(source))

    def test_extracted_sources_are_syntactically_valid(self):
        for path in catalog_sources(generate.TESTERS_DIR):
            with self.subTest(path=path):
                if path.suffix == ".py":
                    compile(path.read_text(), str(path), "exec")
                elif path.suffix == ".sh":
                    subprocess.run(["bash", "-n", str(path)], check=True, capture_output=True)
                elif path.suffix == ".json":
                    json.loads(path.read_text())

    def test_catalog_has_explicit_validation_status(self):
        for target, spec in load_catalog(generate.TESTERS_DIR).items():
            self.assertTrue(spec["blocks"], target)
            for block in spec["blocks"]:
                path = source_path(generate.TESTERS_DIR, block["source"])
                if path.suffix in (".py", ".ts"):
                    self.assertTrue(
                        block.get("execution_pending") or block.get("live_tested") or block.get("existing_python_test"),
                        block["source"],
                    )


class CatalogGenerationTest(unittest.TestCase):
    def test_legacy_exemptions_cannot_expand(self):
        old = {"example.mdx": {"blocks": [{"source": "example.py", "execution_pending": "Needs fixtures"}]}}
        self.assertEqual(check_catalog_migration(old, old), [])
        self.assertTrue(check_catalog_migration(old, {}))
        self.assertTrue(
            check_catalog_migration({"new.mdx": {"blocks": [{"source": "new.py", "existing_python_test": True}]}}, old)
        )
        ready = {
            "example.mdx": {
                "blocks": [{"source": "example.py", "live_tested": True}, {"source": "example.ts", "live_tested": True}]
            }
        }
        self.assertEqual(check_catalog_migration(ready, old), [])

    def test_mixed_language_tabs_keep_order_and_titles(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            testers = root / "testers"
            testers.mkdir()
            (testers / "example.py").write_text("print('hello')\n")
            (testers / "example.sh").write_text("echo hello\n")
            (testers / "snippets.json").write_text(
                json.dumps(
                    {
                        "example.mdx": {
                            "group": True,
                            "blocks": [
                                {"source": "example.sh", "language": "bash", "title": "Shell"},
                                {"source": "example.py", "language": "python", "title": "Python"},
                            ],
                        }
                    }
                )
            )
            with patch.multiple(generate, ROOT_DIR=root, TESTERS_DIR=testers, SNIPPETS_DIR=root / "snippets"):
                self.assertEqual(generate.get_all_tester_files(), [testers / "example.mdx"])
                rendered = generate.render_file(testers / "example.mdx")
                self.assertIn("<CodeGroup>", rendered)
                self.assertLess(rendered.index("```bash Shell"), rendered.index("```python Python"))

    def test_sources_cannot_escape_testers(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "testers").mkdir()
            (root / "outside.py").write_text("print('outside')\n")
            with self.assertRaises(ValueError):
                source_path(root / "testers", "../outside.py")

    def test_missing_source_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):
                source_path(Path(temp), "missing.py")


if __name__ == "__main__":
    unittest.main()
