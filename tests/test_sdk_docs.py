import json
import tempfile
import unittest
from pathlib import Path

from scripts.check_sdk_docs import get_documented_methods_from_docs_json


class SdkDocumentationTests(unittest.TestCase):
    def test_hidden_reference_pages_count_without_accepting_missing_methods(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            docs_json = root / "docs.json"
            docs_json.write_text(
                json.dumps({"navigation": {"tabs": [{"groups": [{"pages": ["sdk-reference/remotesession/scrape"]}]}]}})
            )
            for page in ["nottevault/set_credit_card", "manual/vault", "misc/credential"]:
                target = root / "sdk-reference" / f"{page}.mdx"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("# Reference\n")

            methods = get_documented_methods_from_docs_json(docs_json)

            self.assertEqual(methods, {"scrape", "set_credit_card"})
            self.assertNotIn("undocumented_method", methods)
