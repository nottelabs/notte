"""Deployment examples retain their lesson and clean up their owned functions."""

import json
import unittest
from pathlib import Path

from parser import parse_file

ROOT = Path(__file__).resolve().parents[1]
CASES = {
    "deploy_function": ("my_automation.py", "Search Automation"),
    "creating/deploy_sdk": ("scraper_function.py", "Website Scraper"),
    "creating/deployment_options": ("my_function.py", "My Function"),
    "management/private_function": ("my_function.py", "Private Automation"),
}


class DeploymentPairsTest(unittest.TestCase):
    def test_deployment_contracts_match_names_and_keep_functions_private(self):
        contracts = json.loads((ROOT / "sniptest/live-examples.json").read_text())
        for name, (filename, title) in CASES.items():
            expected = contracts[f"functions/{name}.ts"]["expected"]["results"]
            self.assertEqual(expected[0], title)
            self.assertIs(expected[2], False)
            self.assertEqual(expected[3], "paired deployment")
            for suffix in (".py", ".ts"):
                with self.subTest(name=name, language=suffix):
                    path = ROOT / "testers/functions" / (name + suffix)
                    config, rendered = parse_file(path)
                    self.assertIsNotNone(config.show)
                    self.assertIn(filename, rendered)
                    self.assertIn(title, rendered)
                    for hidden in ("paired deployment", "finally", ".delete()", "export {", "results ="):
                        self.assertNotIn(hidden, rendered)
                    self.assertIn("finally", path.read_text())
                    self.assertIn(".delete()", path.read_text())

    def test_deployments_keep_version_output_in_both_languages(self):
        for name in ("deploy_function", "creating/deploy_sdk"):
            for suffix in (".py", ".ts"):
                _, rendered = parse_file(ROOT / "testers/functions" / (name + suffix))
                self.assertIn("Function deployed:", rendered)
                self.assertIn("Version:", rendered)
                self.assertIn("latest_version", rendered)
