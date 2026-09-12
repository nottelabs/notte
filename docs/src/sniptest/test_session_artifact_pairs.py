"""Keep session artifact examples focused and their lifecycle checks complete."""

import json
import unittest
from pathlib import Path

from parser import parse_file

CASES = (
    "sessions/cdp",
    "sessions/configuration/cookie_file",
    "sessions/cdp/selenium_builtin_page",
    "sessions/capabilities/match_viewport",
    "sessions/stealth/match_viewport",
)


class SessionArtifactPairsTest(unittest.TestCase):
    def test_pairs_hide_capture_and_use_closed_session_contracts(self):
        root = Path(__file__).resolve().parents[1]
        contracts = json.loads((root / "sniptest/live-examples.json").read_text())
        for name in CASES:
            self.assertEqual(contracts[name + ".ts"], {"expected": {"status": "closed"}, "closedSession": True})
            for suffix in (".py", ".ts"):
                with self.subTest(name=name, suffix=suffix):
                    config, rendered = parse_file(root / "testers" / (name + suffix))
                    self.assertIsNotNone(config.show)
                    for hidden in ("status =", "return await", "export {", "sniptest_cookie", "idle_timeout_minutes"):
                        self.assertNotIn(hidden, rendered)

    def test_viewports_retain_both_session_ids_for_cleanup(self):
        root = Path(__file__).resolve().parents[1] / "testers"
        for name in ("sessions/capabilities/match_viewport", "sessions/stealth/match_viewport"):
            python = (root / (name + ".py")).read_text()
            typescript = (root / (name + ".ts")).read_text()
            self.assertIn("results = [desktop_status.session_id, status.session_id]", python)
            self.assertIn("results = [desktopStatus.session_id, status.session_id]", typescript)
            for value in ("1920", "1080", "1366", "768"):
                self.assertIn(value, python)
                self.assertIn(value, typescript)
