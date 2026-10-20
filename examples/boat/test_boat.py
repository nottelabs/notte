import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import main as demo
from dotenv import load_dotenv

# Read keys from .env, as main.py does, so the live test runs when they are set there.
load_dotenv()

TEST_KEY = "test-only"  # pragma: allowlist secret
URL = "https://sandbox-8000.on.boat.dev?_token=secret"  # pragma: allowlist secret


class FakeBoat:
    """Records boat API calls and fails the commands listed in `failing`."""

    def __init__(self, failing=()):
        self.failing = set(failing)
        self.created = []
        self.files = []
        self.detached = []
        self.runs = []
        self.hosted = []
        self.deleted = []

    def create(self, create_sandbox_request):
        self.created.append(create_sandbox_request)
        return SimpleNamespace(sandbox=SimpleNamespace(id="sb-1"))

    def command(self, sandbox_id, request):
        self.detached.append(request)
        return SimpleNamespace(actual_instance=SimpleNamespace(process_id="p-1"))

    def host_port(self, sandbox_id, request):
        self.hosted.append(request)
        return SimpleNamespace(url=URL)

    def delete_sandbox(self, x_ascii_confirm_delete, sandbox_id):
        self.deleted.append((x_ascii_confirm_delete, sandbox_id))

    def exec(self, command):
        self.runs.append(command)
        if command in self.failing:
            return SimpleNamespace(exit_code=1, stdout="", stderr=f"{command} failed\n")
        if command == "notte sessions start -o json":
            return SimpleNamespace(exit_code=0, stdout=json.dumps({"session_id": "s-1"}), stderr="")
        return SimpleNamespace(exit_code=0, stdout=f"output of {command}\n", stderr="")


def fake_exec(boat, sandbox_id, command, cwd=None, timeout_seconds=30):
    return SimpleNamespace(actual_instance=boat.exec(command))


def fake_write(boat, sandbox_id, path, content):
    boat.files.append((path, content))


@patch.dict(os.environ, {"NOTTE_API_KEY": TEST_KEY})
@patch.object(demo, "exec_command", fake_exec)
@patch.object(demo, "write_text", fake_write)
@patch.object(demo, "wait_until_ready", lambda boat, sandbox_id: None)
class OfflineTests(unittest.TestCase):
    def test_sandbox_gets_the_notte_key_in_its_environment(self):
        os.environ.pop("NOTTE_API_URL", None)
        boat = FakeBoat()
        self.assertEqual(demo.create_sandbox(boat), "sb-1")
        self.assertEqual(boat.created[0].env, {"NOTTE_API_KEY": TEST_KEY})

    def test_sandbox_gets_an_explicit_api_url(self):
        boat = FakeBoat()
        with patch.dict(os.environ, {"NOTTE_API_URL": "https://example.test"}):
            demo.create_sandbox(boat)
        self.assertEqual(boat.created[0].env["NOTTE_API_URL"], "https://example.test")

    def test_app_is_served_in_the_background_on_a_hosted_url(self):
        boat = FakeBoat()
        self.assertEqual(demo.start_app(boat, "sb-1"), URL)
        self.assertEqual(boat.files, [(f"{demo.APP_DIR}/index.html", demo.APP_HTML)])
        server = boat.detached[0]
        self.assertEqual((server.command, server.cwd, server.detached), ("python3 -m http.server 8000", "app", True))
        self.assertIn("curl -sf http://localhost:8000", boat.runs[0])
        self.assertEqual(boat.hosted[0].port, 8000)
        self.assertFalse(boat.hosted[0].public)

    def test_app_that_never_starts_raises(self):
        boat = FakeBoat()
        boat.exec = lambda command: SimpleNamespace(exit_code=1, stdout="", stderr="")
        with self.assertRaisesRegex(demo.CommandError, "exited with 1"):
            demo.start_app(boat, "sb-1")

    def test_cli_runs_the_agent_commands_and_stops_the_session(self):
        boat = FakeBoat()
        output = demo.check_with_notte_cli(boat, "sb-1", URL)
        self.assertEqual(
            boat.runs,
            [
                "notte sessions start -o json",
                f"notte page goto '{URL}'",
                "notte page fill '#title' 'Ship the boat example'",
                "notte page click 'button[type=submit]'",
                "notte page scrape --only-main-content",
                "notte sessions stop --yes",
            ],
        )
        self.assertEqual(output, "output of notte page scrape --only-main-content")

    def test_cli_output_never_prints_the_hosted_url_token(self):
        boat = FakeBoat()
        with patch("builtins.print") as printed:
            demo.check_with_notte_cli(boat, "sb-1", URL)
        self.assertNotIn("_token=secret", " ".join(str(call) for call in printed.call_args_list))

    def test_sandbox_that_never_gets_ready_is_deleted(self):
        boat = FakeBoat()

        def not_ready(boat, sandbox_id):
            raise TimeoutError("not ready")

        with patch.object(demo, "wait_until_ready", not_ready), self.assertRaises(TimeoutError):
            demo.create_sandbox(boat)
        self.assertEqual(boat.deleted, [("sb-1", "sb-1")])

    def test_failed_delete_does_not_hide_the_startup_error(self):
        boat = FakeBoat()

        def not_ready(boat, sandbox_id):
            raise TimeoutError("not ready")

        def delete_fails(x_ascii_confirm_delete, sandbox_id):
            raise RuntimeError("delete failed")

        boat.delete_sandbox = delete_fails
        with patch.object(demo, "wait_until_ready", not_ready), self.assertRaisesRegex(TimeoutError, "not ready"):
            demo.create_sandbox(boat)

    def test_failed_navigation_keeps_the_token_out_of_the_error(self):
        boat = FakeBoat(failing={f"notte page goto '{URL}'"})
        with self.assertRaises(demo.CommandError) as raised:
            demo.check_with_notte_cli(boat, "sb-1", URL)
        self.assertNotIn("_token=secret", str(raised.exception))
        self.assertIn("<hosted URL>", str(raised.exception))

    def test_failed_command_still_stops_the_session(self):
        boat = FakeBoat(failing={"notte page click 'button[type=submit]'"})
        with self.assertRaisesRegex(demo.CommandError, "click"):
            demo.check_with_notte_cli(boat, "sb-1", URL)
        self.assertEqual(boat.runs[-1], "notte sessions stop --yes")

    def test_failed_stop_does_not_hide_the_original_error(self):
        boat = FakeBoat(failing={f"notte page goto '{URL}'", "notte sessions stop --yes"})
        with self.assertRaisesRegex(demo.CommandError, "goto"):
            demo.check_with_notte_cli(boat, "sb-1", URL)


@unittest.skipUnless(
    os.environ.get("BOAT_API_KEY") and os.environ.get("NOTTE_API_KEY"), "Needs real boat and Notte API keys"
)
class LiveTests(unittest.TestCase):
    def test_both_browsers_see_the_sandbox_app(self):
        notte = demo.NotteClient()
        config = demo.Configuration(host="https://boat.dev/api/v1", access_token=os.environ["BOAT_API_KEY"])
        with demo.ApiClient(config) as client:
            boat = demo.BoatApi(client)
            sandbox_id = demo.create_sandbox(boat)
            try:
                url = demo.start_app(boat, sandbox_id)
                self.assertEqual(demo.check_with_playwright(notte, url), ["Write the app", "Start the server"])
                demo.install_notte(boat, sandbox_id)
                # The CLI wraps long lines, so compare without line breaks.
                page = demo.check_with_notte_cli(boat, sandbox_id, url).replace("\n", " ")
                self.assertIn("Ship the boat example", page)
                self.assertIn("3 to-dos", page)
            finally:
                boat.delete_sandbox(x_ascii_confirm_delete=sandbox_id, sandbox_id=sandbox_id)


if __name__ == "__main__":
    unittest.main()
