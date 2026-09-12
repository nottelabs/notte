"""Regression coverage for the browser-action and session-settings batch."""

import ast
import json
import re
import unittest
from pathlib import Path

from parser import parse_file

CASES = [
    "browser-controls/goto",
    "browser-controls/reload",
    "browser-controls/scroll_down",
    "browser-controls/scroll_up",
    "browser-controls/press_key",
    "browser-controls/wait",
    "guides/wait_time",
    "sessions/capabilities/captcha_combine_stealth",
    "sessions/captcha/combine_stealth",
    "sessions/capabilities/captcha_ensure_requirements",
    "sessions/captcha/ensure_requirements",
    "sessions/capabilities/captcha_increase_timeout",
    "sessions/capabilities/combine_stealth",
    "sessions/stealth/combine_techniques",
    "sessions/default_proxy",
    "sessions/stealth_configuration",
    "sessions/capabilities/dev_environment",
]


class BrowserSettingsPairsTest(unittest.TestCase):
    def test_pairs_have_live_contracts_and_hide_test_checks(self):
        root = Path(__file__).resolve().parents[1]
        contracts = json.loads((root / "sniptest/live-examples.json").read_text())
        for name in CASES:
            with self.subTest(name=name):
                self.assertTrue(contracts[name + ".ts"]["closedSession"])
                for suffix in (".py", ".ts"):
                    config, rendered = parse_file(root / "testers" / (name + suffix))
                    self.assertIsNotNone(config.show)
                    for hidden in ("assert ", "export {", "status = ", "mismatch", "Session was not closed"):
                        self.assertNotIn(hidden, rendered)
                    if suffix == ".ts":
                        self.assertIn("await session.use", rendered)
                        self.assertIn("});", rendered)

    def test_actions_and_session_options_match_python(self):
        root = Path(__file__).resolve().parents[1] / "testers"
        for name in CASES:
            with self.subTest(name=name):
                python = (root / (name + ".py")).read_text()
                _, typescript = parse_file(root / (name + ".ts"))
                actions = []
                for node in ast.walk(ast.parse(python)):
                    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                        continue
                    if node.func.attr not in ("execute", "Session", "observe"):
                        continue
                    for keyword in node.keywords:
                        if not isinstance(keyword.value, ast.Constant):
                            continue
                        value = keyword.value.value
                        if keyword.arg == "type":
                            actions.append(value)
                        if node.func.attr == "observe" and keyword.arg == "url":
                            actions.append("goto")
                        if keyword.arg == "proxies" and value == "us":
                            self.assertIn("country: 'us'", typescript)
                        elif isinstance(value, bool):
                            self.assertIn(f"{keyword.arg}: {str(value).lower()}", typescript)
                        else:
                            self.assertIn(str(value), typescript)
                self.assertEqual(actions, re.findall(r'execute[(][{] type: ["\']([^"\']+)["\']', typescript))

    def test_scroll_examples_use_a_scrollable_page_and_scroll_down_before_up(self):
        root = Path(__file__).resolve().parents[1] / "testers/browser-controls"
        for suffix in (".py", ".ts"):
            for name in ("scroll_down", "scroll_up"):
                _, rendered = parse_file(root / (name + suffix))
                self.assertIn("https://en.wikipedia.org/wiki/Web_browser", rendered)
                if name == "scroll_up":
                    self.assertLess(rendered.index('"scroll_down"'), rendered.index('"scroll_up"'))
