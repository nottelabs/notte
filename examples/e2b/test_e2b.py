import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import main as demo
from e2b import CommandExitException

TEST_KEY = "test-only"  # pragma: allowlist secret


class FakeSandbox:
    """Records sandbox calls and fails the commands listed in `failing`."""

    def __init__(self, failing=()):
        self.failing = set(failing)
        self.writes = []
        self.runs = []
        self.files = SimpleNamespace(write=lambda path, content: self.writes.append((path, content)))
        self.commands = SimpleNamespace(run=self.run)

    def run(self, command, **kwargs):
        self.runs.append((command, kwargs))
        if command in self.failing:
            raise CommandExitException(stderr=f"{command} failed\n", stdout="", exit_code=1, error=None)
        if command == "notte sessions start -o json":
            return SimpleNamespace(stdout='{"session_id": "s-1", "viewer_url": "https://viewer"}')
        return SimpleNamespace(stdout=f"output of {command}\n")

    def get_host(self, port):
        return f"{port}-sandbox.e2b.app"

    def commands_run(self):
        return [command for command, _ in self.runs]


@patch.dict(os.environ, {"NOTTE_API_KEY": TEST_KEY})
class OfflineTests(unittest.TestCase):
    def test_app_is_served_in_the_background_on_the_public_url(self):
        sandbox = FakeSandbox()
        url = demo.start_app(sandbox)
        self.assertEqual(url, "https://8000-sandbox.e2b.app")
        self.assertEqual(sandbox.writes, [(f"{demo.APP_DIR}/index.html", demo.APP_HTML)])
        server, server_kwargs = sandbox.runs[0]
        self.assertEqual(server, "python3 -m http.server 8000")
        self.assertEqual(server_kwargs, {"cwd": demo.APP_DIR, "background": True})
        self.assertIn("curl -sf http://localhost:8000", sandbox.runs[1][0])

    def test_cli_runs_the_agent_commands_and_stops_the_session(self):
        sandbox = FakeSandbox()
        output = demo.check_with_notte_cli(sandbox, "https://8000-sandbox.e2b.app")
        self.assertEqual(
            sandbox.commands_run(),
            [
                "notte sessions start -o json",
                "notte page goto https://8000-sandbox.e2b.app",
                "notte page fill '#title' 'Ship the E2B example'",
                "notte page click 'button[type=submit]'",
                "notte page scrape --only-main-content",
                "notte sessions stop --yes",
            ],
        )
        self.assertEqual(output, "output of notte page scrape --only-main-content")
        self.assertTrue(all(kwargs["envs"]["NOTTE_API_KEY"] == TEST_KEY for _, kwargs in sandbox.runs))

    def test_cli_forwards_an_explicit_api_url(self):
        sandbox = FakeSandbox()
        with patch.dict(os.environ, {"NOTTE_API_URL": "https://example.test"}):
            demo.check_with_notte_cli(sandbox, "https://8000-sandbox.e2b.app")
        self.assertTrue(all(kwargs["envs"]["NOTTE_API_URL"] == "https://example.test" for _, kwargs in sandbox.runs))

    def test_failed_command_still_stops_the_session(self):
        sandbox = FakeSandbox(failing={"notte page click 'button[type=submit]'"})
        with self.assertRaisesRegex(CommandExitException, "click"):
            demo.check_with_notte_cli(sandbox, "https://8000-sandbox.e2b.app")
        self.assertEqual(sandbox.commands_run()[-1], "notte sessions stop --yes")

    def test_failed_stop_does_not_hide_the_original_error(self):
        sandbox = FakeSandbox(failing={"notte page goto https://8000-sandbox.e2b.app", "notte sessions stop --yes"})
        with self.assertRaisesRegex(CommandExitException, "goto"):
            demo.check_with_notte_cli(sandbox, "https://8000-sandbox.e2b.app")


@unittest.skipUnless(
    os.environ.get("E2B_API_KEY") and os.environ.get("NOTTE_API_KEY"), "Needs real E2B and Notte API keys"
)
class LiveTests(unittest.TestCase):
    def test_both_browsers_see_the_sandbox_app(self):
        notte = demo.NotteClient()
        sandbox = demo.Sandbox.create(timeout=300)
        try:
            url = demo.start_app(sandbox)
            self.assertEqual(demo.check_with_playwright(notte, url), ["Write the app", "Start the server"])
            demo.install_notte(sandbox)
            # The CLI wraps long lines, so compare without line breaks.
            page = demo.check_with_notte_cli(sandbox, url).replace("\n", "")
            self.assertIn("Ship the E2B example", page)
            self.assertIn("3 to-dos", page)
        finally:
            sandbox.kill()


if __name__ == "__main__":
    unittest.main()
