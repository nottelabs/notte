"""Keep browser behavior and lightweight configuration examples paired."""

import json
import unittest
from pathlib import Path

from parser import parse_file

CASES = (
    "browser-controls/conditional_actions",
    "browser-controls/eval_js",
    "sessions/country_proxy",
)
ROOT = Path(__file__).resolve().parents[1]


class BrowserConfigPairsTest(unittest.TestCase):
    def test_contracts_hide_auxiliary_checks(self):
        contracts = json.loads((ROOT / "sniptest/live-examples.json").read_text())
        for name in CASES:
            with self.subTest(name=name):
                self.assertIn(name + ".ts", contracts)
                for suffix in (".py", ".ts"):
                    config, rendered = parse_file(ROOT / "testers" / (name + suffix))
                    self.assertIsNotNone(config.show)
                    for hidden in ("assert ", "throw new Error", "status =", "results =", "export {", "status.steps"):
                        self.assertNotIn(hidden, rendered)
                if name.startswith("browser-controls/"):
                    self.assertTrue(contracts[name + ".ts"]["closedSession"])
                    self.assertTrue(rendered.rstrip().removesuffix("```").rstrip().endswith("});"))
                else:
                    self.assertNotIn("closedSession", contracts[name + ".ts"])

    def test_browser_examples_preserve_urls_operations_and_branches(self):
        for suffix in (".py", ".ts"):
            _, conditional = parse_file(ROOT / "testers/browser-controls" / ("conditional_actions" + suffix))
            for text in (
                "https://example.com",
                "button.optional",
                "button.next",
                "Optional button not found, continuing...",
            ):
                self.assertIn(text, conditional)
            _, evaluation = parse_file(ROOT / "testers/browser-controls" / ("eval_js" + suffix))
            for text in (
                "https://notte.cc/",
                "document.title",
                "Array.from(document.querySelectorAll('a')).map(a => a.href)",
            ):
                self.assertIn(text, evaluation)
