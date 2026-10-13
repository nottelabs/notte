"""Hidden reference pages still satisfy example documentation coverage."""

import importlib.util
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "check_sdk_docs", Path(__file__).resolve().parents[3] / "scripts/check_sdk_docs.py"
)
assert spec and spec.loader
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


class ReferenceCoverageTest(unittest.TestCase):
    def test_hidden_method_page_counts_but_absent_method_does_not(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "docs.json"
            config.write_text('{"navigation": {"tabs": []}}')
            page = root / "sdk-reference/nottevault/set_credit_card.mdx"
            page.parent.mkdir(parents=True)
            page.write_text("---\ntitle: set_credit_card\n---\nSet a credit card.")
            self.assertIn("set_credit_card", checker.get_documented_methods_from_docs_json(config))
            self.assertNotIn("missing_method", checker.get_documented_methods_from_docs_json(config))
            page.unlink()
            self.assertNotIn("set_credit_card", checker.get_documented_methods_from_docs_json(config))
