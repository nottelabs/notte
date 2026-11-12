import json
import os
import re
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import main as demo
from boxd import Boxd
from boxd.errors import NotFoundError
from dotenv import load_dotenv

# Read keys from .env, as main.py does, so the live test runs when they are set there.
load_dotenv()

TEST_KEY = "test-only"  # pragma: allowlist secret
URL = "https://notte-example-1.boxd.sh"
SCRAPE = "notte page scrape --only-main-content"
# What the CLI prints for the app after the new to-do, wrapped as the CLI wraps it.
SCRAPED_PAGE = "Sandbox To-dos Add Write the app Start the server Ship the boxd example 3 to-\ndos\n"
DOCS_PAGE = Path(__file__).resolve().parent.parent.parent / "docs/src/integrations/boxd.mdx"


class FakeMachines:
    """Records boxd machine calls, fails the commands in `failing` and answers those in `outputs`."""

    def __init__(self, failing=(), outputs=None):
        self.failing = set(failing)
        self.outputs = outputs or {}
        self.created = []
        self.uploads = []
        self.runs = []
        self.envs = []
        self.cwds = []
        self.bot_protection = []
        self.deleted = []
        self.files = SimpleNamespace(upload=self.upload)

    def machine(self, machine_id="m-1"):
        return SimpleNamespace(id=machine_id, name="notte-example-1", access=SimpleNamespace(url=URL))

    def create(self, name, org=None, isolated=False, delete_after=None):
        self.created.append({"name": name, "org": org, "isolated": isolated, "delete_after": delete_after})
        return self.machine()

    def wait_until_ready(self, machine_id):
        return self.machine(machine_id)

    def set_bot_protection(self, machine_id, mode):
        self.bot_protection.append((machine_id, mode))

    def upload(self, machine_id, path, data):
        self.uploads.append((path, data))

    def delete(self, machine_id):
        self.deleted.append(machine_id)

    def exec(self, machine_id, command, env=None, cwd=None, timeout=None):
        self.runs.append(command)
        self.cwds.append(cwd)
        self.envs.append(env)
        if command in self.failing:
            return SimpleNamespace(exit_code=1, stdout="", stderr=f"{command} failed\n")
        if command == "notte sessions start -o json":
            return SimpleNamespace(exit_code=0, stdout=json.dumps({"session_id": "s-1"}), stderr="")
        if command in self.outputs:
            return SimpleNamespace(exit_code=0, stdout=self.outputs[command], stderr="")
        return SimpleNamespace(exit_code=0, stdout=f"output of {command}\n", stderr="")


def fake_boxd(failing=(), outputs=None):
    return SimpleNamespace(machines=FakeMachines(failing, outputs))


def run_main(boxd, todos=demo.TODOS):
    """Run main() against the fake machines, with Playwright reporting `todos`."""
    with (
        patch.object(demo, "Boxd", return_value=boxd),
        patch.object(demo, "NotteClient"),
        patch.object(demo, "load_dotenv"),
        patch.object(demo, "check_with_playwright", return_value=list(todos)),
    ):
        demo.main()


@patch.dict(os.environ, {"NOTTE_API_KEY": TEST_KEY})
class OfflineTests(unittest.TestCase):
    def test_machine_is_isolated_and_named_with_the_prefix(self):
        boxd = fake_boxd()
        with patch.dict(os.environ, {"BOXD_MACHINE_PREFIX": "ci-", "BOXD_ORG": "acme"}):
            machine = demo.create_machine(boxd)
        self.assertEqual(machine.id, "m-1")
        created = boxd.machines.created[0]
        self.assertTrue(created["isolated"])
        self.assertEqual(created["org"], "acme")
        self.assertRegex(created["name"], r"^ci-[0-9a-f]{8}$")

    def test_machine_names_are_unique(self):
        boxd = fake_boxd()
        os.environ.pop("BOXD_MACHINE_PREFIX", None)
        demo.create_machine(boxd)
        demo.create_machine(boxd)
        first, second = (created["name"] for created in boxd.machines.created)
        self.assertTrue(first.startswith("notte-example-"))
        self.assertNotEqual(first, second)

    def test_machine_deletes_itself_after_30_minutes(self):
        boxd = fake_boxd()
        demo.create_machine(boxd)
        self.assertEqual(boxd.machines.created[0]["delete_after"], 1800)

    def test_machine_url_skips_the_browser_check(self):
        boxd = fake_boxd()
        demo.create_machine(boxd)
        self.assertEqual(boxd.machines.bot_protection, [("m-1", "off")])

    def test_app_is_served_in_the_background_on_the_machine_url(self):
        boxd = fake_boxd()
        self.assertEqual(demo.start_app(boxd, boxd.machines.machine()), URL)
        self.assertEqual(boxd.machines.uploads, [(f"{demo.APP_DIR}/index.html", demo.APP_HTML)])
        self.assertEqual(boxd.machines.runs[0], "nohup python3 -m http.server 8000 > /tmp/app.log 2>&1 &")
        self.assertEqual(boxd.machines.cwds[0], demo.APP_DIR)
        self.assertIn("curl -sf http://localhost:8000", boxd.machines.runs[1])

    def test_app_that_never_starts_raises(self):
        boxd = fake_boxd()
        boxd.machines.exec = lambda machine_id, command, env=None, cwd=None, timeout=None: SimpleNamespace(
            exit_code=1, stdout="", stderr=""
        )
        with self.assertRaisesRegex(demo.CommandError, "exited with 1"):
            demo.start_app(boxd, boxd.machines.machine())

    def test_cli_runs_the_agent_commands_and_stops_the_session(self):
        boxd = fake_boxd()
        output = demo.check_with_notte_cli(boxd, "m-1", URL)
        self.assertEqual(
            boxd.machines.runs,
            [
                "notte sessions start -o json",
                f"notte page goto {URL}",
                "notte page fill '#title' 'Ship the boxd example'",
                "notte page click 'button[type=submit]'",
                "notte page scrape --only-main-content",
                "notte sessions stop --yes",
            ],
        )
        self.assertEqual(output, "output of notte page scrape --only-main-content")

    def test_notte_key_goes_with_every_cli_command(self):
        os.environ.pop("NOTTE_API_URL", None)
        boxd = fake_boxd()
        demo.check_with_notte_cli(boxd, "m-1", URL)
        self.assertEqual(boxd.machines.envs, [{"NOTTE_API_KEY": TEST_KEY}] * 6)

    def test_cli_gets_an_explicit_api_url(self):
        boxd = fake_boxd()
        with patch.dict(os.environ, {"NOTTE_API_URL": "https://example.test"}):
            demo.check_with_notte_cli(boxd, "m-1", URL)
        self.assertEqual(boxd.machines.envs[0]["NOTTE_API_URL"], "https://example.test")

    def test_machine_that_never_gets_ready_is_deleted(self):
        boxd = fake_boxd()

        def not_ready(machine_id):
            raise TimeoutError("not ready")

        boxd.machines.wait_until_ready = not_ready
        with self.assertRaises(TimeoutError):
            demo.create_machine(boxd)
        self.assertEqual(boxd.machines.deleted, ["m-1"])

    def test_machine_is_deleted_when_the_wait_is_interrupted(self):
        boxd = fake_boxd()

        def interrupted(machine_id):
            raise KeyboardInterrupt

        boxd.machines.wait_until_ready = interrupted
        with self.assertRaises(KeyboardInterrupt):
            demo.create_machine(boxd)
        self.assertEqual(boxd.machines.deleted, ["m-1"])

    def test_main_deletes_the_machine_when_the_app_fails(self):
        boxd = fake_boxd(failing={"nohup python3 -m http.server 8000 > /tmp/app.log 2>&1 &"})
        with self.assertRaisesRegex(demo.CommandError, "http.server"):
            run_main(boxd)
        self.assertEqual(boxd.machines.deleted, ["m-1"])

    def test_main_passes_when_both_browsers_see_the_app(self):
        boxd = fake_boxd(outputs={SCRAPE: SCRAPED_PAGE})
        run_main(boxd)
        self.assertEqual(boxd.machines.deleted, ["m-1"])

    def test_main_fails_when_playwright_sees_other_todos(self):
        boxd = fake_boxd(outputs={SCRAPE: SCRAPED_PAGE})
        with self.assertRaisesRegex(demo.CheckError, "Playwright saw"):
            run_main(boxd, todos=["Write the app"])
        self.assertEqual(boxd.machines.deleted, ["m-1"])

    def test_main_fails_when_the_cli_does_not_see_the_new_todo(self):
        boxd = fake_boxd(outputs={SCRAPE: "Sandbox To-dos Add Write the app Start the server 2 to-dos\n"})
        with self.assertRaisesRegex(demo.CheckError, "Ship the boxd example"):
            run_main(boxd)
        self.assertEqual(boxd.machines.deleted, ["m-1"])

    def test_main_fails_when_the_cli_sees_the_wrong_count(self):
        boxd = fake_boxd(outputs={SCRAPE: "Sandbox To-dos Add Write the app Ship the boxd example 2 to-dos\n"})
        with self.assertRaisesRegex(demo.CheckError, "3 to-dos"):
            run_main(boxd)
        self.assertEqual(boxd.machines.deleted, ["m-1"])

    def test_cli_count_is_not_matched_inside_a_larger_number(self):
        with self.assertRaisesRegex(demo.CheckError, "3 to-dos"):
            demo.expect_new_todo("Sandbox To-dos Add Ship the boxd example 13 to-dos")

    def test_cli_page_is_compared_across_wrapped_lines(self):
        demo.expect_new_todo("Sandbox To-dos Add Write the app Start the server Ship the\nboxd example 3 to-\ndos\n")

    def test_main_fails_when_only_the_delete_fails(self):
        boxd = fake_boxd(outputs={SCRAPE: SCRAPED_PAGE})

        def delete_fails(machine_id):
            raise RuntimeError("delete failed")

        boxd.machines.delete = delete_fails
        with self.assertRaises(SystemExit) as raised:
            run_main(boxd)
        # A message as the exit code makes Python print it and exit with 1.
        self.assertIn("m-1 was not deleted", str(raised.exception.code))

    def test_failed_delete_does_not_hide_the_run_error(self):
        boxd = fake_boxd(failing={"nohup python3 -m http.server 8000 > /tmp/app.log 2>&1 &"})

        def delete_fails(machine_id):
            raise RuntimeError("delete failed")

        boxd.machines.delete = delete_fails
        with self.assertRaisesRegex(demo.CommandError, "http.server"):
            run_main(boxd)

    def test_failed_delete_does_not_hide_the_startup_error(self):
        boxd = fake_boxd()

        def not_ready(machine_id):
            raise TimeoutError("not ready")

        def delete_fails(machine_id):
            raise RuntimeError("delete failed")

        boxd.machines.wait_until_ready = not_ready
        boxd.machines.delete = delete_fails
        with self.assertRaisesRegex(TimeoutError, "not ready"):
            demo.create_machine(boxd)

    def test_failed_start_still_tries_to_stop_the_session(self):
        boxd = fake_boxd(failing={"notte sessions start -o json"})
        with self.assertRaisesRegex(demo.CommandError, "sessions start"):
            demo.check_with_notte_cli(boxd, "m-1", URL)
        self.assertEqual(boxd.machines.runs[-1], "notte sessions stop --yes")

    def test_failed_command_still_stops_the_session(self):
        boxd = fake_boxd(failing={"notte page click 'button[type=submit]'"})
        with self.assertRaisesRegex(demo.CommandError, "click"):
            demo.check_with_notte_cli(boxd, "m-1", URL)
        self.assertEqual(boxd.machines.runs[-1], "notte sessions stop --yes")

    def test_failed_stop_does_not_hide_the_original_error(self):
        boxd = fake_boxd(failing={f"notte page goto {URL}", "notte sessions stop --yes"})
        with self.assertRaisesRegex(demo.CommandError, "goto"):
            demo.check_with_notte_cli(boxd, "m-1", URL)

    def test_api_error_on_stop_does_not_hide_the_original_error(self):
        boxd = fake_boxd(failing={f"notte page goto {URL}"})
        original = boxd.machines.exec

        def exec_or_api_error(machine_id, command, env=None, cwd=None, timeout=None):
            if command == "notte sessions stop --yes":
                raise ConnectionError("boxd API unavailable")
            return original(machine_id, command, env=env, cwd=cwd, timeout=timeout)

        boxd.machines.exec = exec_or_api_error
        with self.assertRaisesRegex(demo.CommandError, "goto"):
            demo.check_with_notte_cli(boxd, "m-1", URL)


@unittest.skipUnless(DOCS_PAGE.is_file(), "Needs the docs page from the repository")
class DocsPageTests(unittest.TestCase):
    def test_python_snippet_serves_the_elements_the_cli_steps_use(self):
        page = DOCS_PAGE.read_text()
        python = "\n".join(re.findall(r"```python\n(.*?)```", page, re.S))
        bash = "\n".join(re.findall(r"```bash\n(.*?)```", page, re.S))
        self.assertIn("notte page fill '#title'", bash)
        self.assertIn("notte page click 'button[type=submit]'", bash)
        self.assertIn('<input id="title">', python)
        self.assertIn('<button type="submit">', python)


@unittest.skipUnless(
    os.environ.get("BOXD_API_KEY") and os.environ.get("NOTTE_API_KEY"), "Needs real boxd and Notte API keys"
)
class LiveTests(unittest.TestCase):
    def test_both_browsers_see_the_machine_app(self):
        notte = demo.NotteClient()
        boxd = Boxd()
        machine = demo.create_machine(boxd)
        try:
            url = demo.start_app(boxd, machine)
            demo.expect_todos(demo.check_with_playwright(notte, url))
            demo.install_notte(boxd, machine.id)
            demo.expect_new_todo(demo.check_with_notte_cli(boxd, machine.id, url))
        finally:
            demo.delete_machine(boxd, machine.id)
        with self.assertRaises(NotFoundError):
            boxd.machines.get(machine.id)


if __name__ == "__main__":
    unittest.main()
