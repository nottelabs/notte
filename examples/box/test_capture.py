import os
import time
import unittest
from unittest.mock import patch

import main as demo
from notte_sdk import NotteClient


@unittest.skipUnless(os.environ.get("NOTTE_BOX_CAPTURE_LIVE") == "1", "Live browser tests are opt-in")
class CaptureLiveTests(unittest.TestCase):
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
