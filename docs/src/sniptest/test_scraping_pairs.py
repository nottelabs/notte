"""Keep executable scraping pairs aligned without publishing test scaffolding."""

import ast
import json
import unittest
from pathlib import Path

from catalog import execution_backlog
from parser import parse_file

CASES = ("quick_scrape", "quickstart", "simple", "content_filtering", "link_placeholders", "links_and_images")
ROOT = Path(__file__).resolve().parents[1]


class ScrapingPairsTest(unittest.TestCase):
    def test_all_pairs_are_executable_with_content_contracts(self):
        contracts = json.loads((ROOT / "sniptest/live-examples.json").read_text())
        pending = execution_backlog(ROOT / "testers")
        for name in CASES:
            with self.subTest(name=name):
                checks = 4 if name in ("link_placeholders", "links_and_images") else 2
                self.assertEqual(contracts[f"scraping/{name}.ts"]["expected"], {"results": [True] * checks})
                for suffix in ("py", "ts"):
                    path = f"scraping/{name}.{suffix}"
                    self.assertNotIn(path, pending)
                    config, rendered = parse_file(ROOT / "testers" / path)
                    self.assertIsNotNone(config.show)
                    self.assertNotIn("results =", rendered)
                    self.assertNotIn("export ", rendered)

    def test_typescript_preserves_python_scrape_options_and_urls(self):
        for name in CASES:
            with self.subTest(name=name):
                python = (ROOT / "testers/scraping" / f"{name}.py").read_text()
                typescript = (ROOT / "testers/scraping" / f"{name}.ts").read_text()
                for node in ast.walk(ast.parse(python)):
                    if (
                        isinstance(node, ast.Constant)
                        and isinstance(node.value, str)
                        and node.value.startswith("https://")
                    ):
                        self.assertIn(node.value, typescript)
                    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                        continue
                    if node.func.attr != "scrape":
                        continue
                    for keyword in node.keywords:
                        if isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, bool):
                            self.assertIn(f"{keyword.arg}: {str(keyword.value.value).lower()}", typescript)
