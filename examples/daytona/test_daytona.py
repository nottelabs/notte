import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import main as demo

TEST_KEY = "test-only"  # pragma: allowlist secret
URL = "https://3000-token.daytonaproxy01.net"
HEADERS = '\'{"X-Daytona-Skip-Preview-Warning": "true"}\''


class FakeSandbox:
    """Records sandbox calls and fails the commands listed in `failing`."""

    def __init__(self, failing=()):
        self.failing = set(failing)
        self.uploads = []
        self.runs = []
        self.session_commands = []
        self.fs = SimpleNamespace(upload_file=lambda data, path: self.uploads.append((path, data)))
        self.process = SimpleNamespace(
            exec=self.exec,
            create_session=lambda name: None,
            execute_session_command=lambda name, request: self.session_commands.append((name, request)),
        )

    def exec(self, command, env=None, timeout=None):
        self.runs.append((command, env))
        if command in self.failing:
            return SimpleNamespace(exit_code=1, result=f"{command} failed\n")
        if command.startswith("notte sessions start"):
            return SimpleNamespace(
                exit_code=0, result=json.dumps({"session_id": "s-1", "viewer_url": "https://viewer"})
            )
        return SimpleNamespace(exit_code=0, result=f"output of {command}\n")

    def create_signed_preview_url(self, port, expires_in_seconds):
        return SimpleNamespace(url=URL)

    def commands_run(self):
        return [command for command, _ in self.runs]


@patch.dict(os.environ, {"NOTTE_API_KEY": TEST_KEY})
class OfflineTests(unittest.TestCase):
    def test_app_is_served_in_the_background_on_a_signed_preview_url(self):
        sandbox = FakeSandbox()
        url = demo.start_app(sandbox)
        self.assertEqual(url, URL)
        self.assertEqual(sandbox.uploads, [(f"{demo.APP_DIR}/index.html", demo.APP_HTML.encode())])
        name, request = sandbox.session_commands[0]
        self.assertEqual(name, "app")
        self.assertEqual(request.command, f"cd {demo.APP_DIR} && python3 -m http.server 3000")
        self.assertTrue(request.run_async)
        self.assertIn("curl -sf http://localhost:3000", sandbox.runs[0][0])

    def test_app_that_never_starts_raises(self):
        sandbox = FakeSandbox()
        sandbox.process.exec = lambda command, env=None, timeout=None: SimpleNamespace(exit_code=1, result="")
        with self.assertRaisesRegex(demo.CommandError, "exited with 1"):
            demo.start_app(sandbox)

    def test_cli_runs_the_agent_commands_and_stops_the_session(self):
        sandbox = FakeSandbox()
        output = demo.check_with_notte_cli(sandbox, URL)
        self.assertEqual(
            sandbox.commands_run(),
            [
                f"notte sessions start --extra-http-headers {HEADERS} -o json",
                f"notte page goto {URL}",
                "notte page fill '#title' 'Ship the Daytona example'",
                "notte page click 'button[type=submit]'",
                "notte page scrape --only-main-content",
                "notte sessions stop --yes",
            ],
        )
        self.assertEqual(output, "output of notte page scrape --only-main-content")
        self.assertTrue(all(env["NOTTE_API_KEY"] == TEST_KEY for _, env in sandbox.runs))

    def test_cli_forwards_an_explicit_api_url(self):
        sandbox = FakeSandbox()
        with patch.dict(os.environ, {"NOTTE_API_URL": "https://example.test"}):
            demo.check_with_notte_cli(sandbox, URL)
        self.assertTrue(all(env["NOTTE_API_URL"] == "https://example.test" for _, env in sandbox.runs))

    def test_failed_command_still_stops_the_session(self):
        sandbox = FakeSandbox(failing={"notte page click 'button[type=submit]'"})
        with self.assertRaisesRegex(demo.CommandError, "click"):
            demo.check_with_notte_cli(sandbox, URL)
        self.assertEqual(sandbox.commands_run()[-1], "notte sessions stop --yes")

    def test_failed_stop_does_not_hide_the_original_error(self):
        sandbox = FakeSandbox(failing={f"notte page goto {URL}", "notte sessions stop --yes"})
        with self.assertRaisesRegex(demo.CommandError, "goto"):
            demo.check_with_notte_cli(sandbox, URL)


@unittest.skipUnless(
    os.environ.get("DAYTONA_API_KEY") and os.environ.get("NOTTE_API_KEY"), "Needs real Daytona and Notte API keys"
)
class LiveTests(unittest.TestCase):
    def test_both_browsers_see_the_sandbox_app(self):
        notte = demo.NotteClient()
        daytona = demo.Daytona()
        sandbox = daytona.create()
        try:
            url = demo.start_app(sandbox)
            self.assertEqual(demo.check_with_playwright(notte, url), ["Write the app", "Start the server"])
            demo.install_notte(sandbox)
            # The CLI wraps long lines, so compare without line breaks.
            page = demo.check_with_notte_cli(sandbox, url).replace("\n", " ")
            self.assertIn("Ship the Daytona example", page)
            self.assertIn("3 to-dos", page)
        finally:
            daytona.delete(sandbox)


if __name__ == "__main__":
    unittest.main()
