import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import main as demo
from notte_sdk import NotteClient


@unittest.skipUnless(os.environ.get("NOTTE_BOX_CAPTURE_LIVE") == "1", "Live browser tests are opt-in")
class CaptureLiveTests(unittest.TestCase):
    def cleanup_case(self, mode):
        client = NotteClient()
        with tempfile.TemporaryDirectory(prefix="box-owned-test-") as temp:
            journal = Path(temp) / "session"
            try:
                try:
                    result = subprocess.run(
                        [sys.executable, str(Path(__file__).with_name("cleanup_case.py")), mode],
                        env={**os.environ, "NOTTE_BOX_TEST_JOURNAL": str(journal)},
                        capture_output=True,
                        text=True,
                        timeout=45,
                    )
                except subprocess.TimeoutExpired:
                    self.fail("Native browser cleanup exceeded its deadline; output withheld")
                self.assertEqual(result.returncode, 0, "Native cleanup failed; SDK output withheld")
                self.assertFalse("PRIVATE_" in result.stdout + result.stderr, "Private output withheld")
                self.assertFalse(
                    os.environ["NOTTE_API_KEY"] in result.stdout + result.stderr, "Credential output withheld"
                )
                row = json.loads(result.stdout.strip().splitlines()[-1])
                self.assertTrue(row["closed"])
                self.assertEqual(client.sessions.status(row["session_id"]).status, "closed")
            finally:
                # A negative baseline must not leave its own allocation active.
                if journal.exists():
                    owned_id = journal.read_text().strip()
                    if client.sessions.status(owned_id).status != "closed":
                        client.sessions.stop(owned_id)
                        self.assertEqual(client.sessions.status(owned_id).status, "closed")

    def test_navigation_and_disconnect_failures_remain_private(self):
        self.cleanup_case("navigation")

    def test_stalled_disconnect_releases_its_owned_browser(self):
        self.cleanup_case("close-timeout")

    def test_disconnect_failure_remains_private_and_releases_browser(self):
        self.cleanup_case("close-error")

    def test_actual_capture_closes_its_owned_browser(self):
        self.assertTrue(os.environ.get("NOTTE_API_URL"), "Choose the test API explicitly")
        client = NotteClient()
        start, ids = client.sessions.start, []

        def track(*args, **kwargs):
            response = start(*args, **kwargs)
            ids.append(response.session_id)
            return response

        with (
            patch.object(client.sessions, "start", side_effect=track),
            patch.object(demo, "NotteClient", return_value=client),
        ):
            try:
                image, session_id = demo.capture_page()
                self.assertTrue(image.startswith(b"\x89PNG\r\n\x1a\n"))
                self.assertGreater(len(image), 1000)
                self.assertEqual(ids, [session_id])
            finally:
                self.assertEqual(len(ids), 1)
                for _ in range(30):
                    status = client.sessions.status(session_id=ids[0])
                    if status.status == "closed":
                        break
                    time.sleep(0.5)
                self.assertEqual(status.status, "closed", "Owned browser did not close")


if __name__ == "__main__":
    unittest.main()
