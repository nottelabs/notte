"""Offline recipe boundaries; real browser acceptance lives in the dedicated workflow."""

import json
import runpy
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


class RecipeTests(unittest.TestCase):
    def test_private_cli_transport_and_cleanup_error_precedence(self):
        for mode in ("success", "invalid_title", "close_failure", "both", "invalid_json"):
            with self.subTest(mode=mode):
                self.check_recipe(mode)

    def check_recipe(self, mode):
        cdp = "wss://fixture.invalid/browser?capability=private-fixture"
        calls = []

        class Session:
            session_id = "owned-fixture"
            closed = False
            error = None

            def __enter__(self):
                return self

            def __exit__(self, _type, error, _traceback):
                self.closed = True
                self.error = error

            def cdp_url(self):
                return cdp

        def execute(args, **kwargs):
            self.assertNotIn(cdp, args, "Authenticated connection must not enter process arguments")
            self.assertEqual(kwargs["env"]["AGENT_BROWSER_CDP"], cdp)
            command = args[4]
            calls.append(command)
            if command == "open" and mode == "invalid_json":
                return SimpleNamespace(returncode=0, stdout=cdp)
            if command == "close" and mode in {"close_failure", "both"}:
                return SimpleNamespace(returncode=1, stdout=json.dumps({"success": False, "error": cdp}))
            title = 42 if mode in {"invalid_title", "both"} else "Example Domain"
            return SimpleNamespace(returncode=0, stdout=json.dumps({"success": True, "data": {"title": title}}))

        session = Session()
        client = SimpleNamespace(Session=lambda: session)
        path = Path(__file__).resolve().parents[2] / "docs/src/testers/integrations/agent_browser.py"
        with patch("notte_sdk.NotteClient", return_value=client), patch("subprocess.run", side_effect=execute):
            if mode == "success":
                result = runpy.run_path(str(path))["result"]
                self.assertEqual(result, {"title": "Example Domain", "session_id": session.session_id})
            else:
                expected = (
                    "The title was not returned"
                    if mode in {"invalid_title", "both"}
                    else "agent-browser command failed"
                )
                with self.assertRaisesRegex(RuntimeError, f"^{expected}$"):
                    runpy.run_path(str(path))
        self.assertEqual(calls[-1], "close", "Every recipe outcome must attempt CLI disconnect")
        self.assertTrue(session.closed, "The surrounding owner must close even when CLI disconnect fails")
        self.assertNotIn(cdp, str(session.error))


if __name__ == "__main__":
    unittest.main()
