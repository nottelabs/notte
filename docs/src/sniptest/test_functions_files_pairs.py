"""Display regressions for file fixtures and function history examples."""

import unittest
from pathlib import Path

from parser import parse_file


class FunctionsFilesPairsTest(unittest.TestCase):
    def test_owned_fixture_setup_stays_out_of_documentation(self):
        root = Path(__file__).resolve().parents[1] / "testers"
        for name in (
            "file-storage/uploading_files",
            "file-storage/attach_before_starting",
            "functions/management/filter_active_runs",
        ):
            for suffix in (".py", ".ts"):
                with self.subTest(name=name, language=suffix):
                    config, rendered = parse_file(root / f"{name}{suffix}")
                    self.assertIsNotNone(config.show)
                    for hidden in ("assert", "export {", "NOTTE_FUNCTION_ID", "FixtureClient", "verified"):
                        self.assertNotIn(hidden, rendered)
                    if "filter_active" in name:
                        self.assertIn("only_active", rendered)
                        self.assertIn("Active runs:", rendered)
                    else:
                        self.assertIn(".upload(", rendered)
                        if suffix == ".py":
                            self.assertNotIn("status = session.status()", rendered)
