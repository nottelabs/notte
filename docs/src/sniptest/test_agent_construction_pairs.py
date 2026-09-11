"""Keep agent construction teaching code aligned across SDKs."""

import unittest
from pathlib import Path

from parser import parse_file


class AgentConstructionPairsTest(unittest.TestCase):
    def test_displayed_options_match_without_test_scaffolding(self):
        root = Path(__file__).resolve().parents[1] / "testers/agents/config"
        cases = {
            "creating_agent": ("gemini/gemini-2.0-flash", "use_vision", "max_steps", "15", "Optional"),
            "param_reasoning_model": ("anthropic/claude-3.5-sonnet",),
            "bp_vision": ("Text-only site", "Image-heavy site", "use_vision"),
        }
        for name, expected in cases.items():
            for suffix in (".py", ".ts"):
                with self.subTest(name=name, language=suffix):
                    config, rendered = parse_file(root / f"{name}{suffix}")
                    self.assertIsNotNone(config.show)
                    for text in expected:
                        self.assertIn(text, rendered)
                    for hidden in ("assert", "export {", "sessionStatus", "status =", "idle_timeout_minutes"):
                        self.assertNotIn(hidden, rendered)
                    if name == "bp_vision":
                        self.assertIn("False" if suffix == ".py" else "false", rendered)
                        self.assertIn("True" if suffix == ".py" else "true", rendered)
