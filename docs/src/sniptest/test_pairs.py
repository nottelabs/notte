"""Offline regression tests for paired example generation and parity enforcement."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import generate
from catalog import catalog_sources
from parity import check_parity
from parser import parse_file


class RepositoryExamplesTest(unittest.TestCase):
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
