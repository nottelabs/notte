import os
import time
import unittest
import uuid
from contextlib import contextmanager
from unittest.mock import patch

import main as demo
import requests
from notte_sdk import NotteClient


@unittest.skipUnless(os.environ.get("NOTTE_BOX_LIVE") == "1", "Live Box tests are opt-in")
class BoxLiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not os.environ.get("BOX_ACCESS_TOKEN") or not os.environ.get("NOTTE_API_URL"):
            raise RuntimeError("Set BOX_ACCESS_TOKEN and choose NOTTE_API_URL explicitly")
        cls.headers = {"Authorization": f"Bearer {os.environ['BOX_ACCESS_TOKEN']}"}
        response = requests.post(
            "https://api.box.com/2.0/folders",
            headers=cls.headers,
            json={"name": f"notte-test-{uuid.uuid4().hex}", "parent": {"id": os.getenv("BOX_FOLDER_ID", "0")}},
            timeout=30,
        )
        if response.status_code != 201:
            raise RuntimeError("Could not create the isolated Box test folder")
        cls.folder_id = response.json()["id"]
        cls.files = []

    @classmethod
    def tearDownClass(cls):
        for file_id in cls.files:
            response = requests.delete(f"https://api.box.com/2.0/files/{file_id}", headers=cls.headers, timeout=30)
            if response.status_code != 204:
                raise RuntimeError("Could not remove a test-owned Box file")
        response = requests.delete(f"https://api.box.com/2.0/folders/{cls.folder_id}", headers=cls.headers, timeout=30)
        if response.status_code != 204:
            raise RuntimeError("Could not remove the empty test-owned Box folder")

    @contextmanager
    def owned(self, folder_id):
        client = NotteClient()
        start, post = client.sessions.start, requests.post
        ids, uploads = [], []

        def track_start(*args, **kwargs):
            response = start(*args, **kwargs)
            ids.append(response.session_id)
            return response

        def track_upload(*args, **kwargs):
            response = post(*args, **kwargs)
            if args[0] == "https://upload.box.com/api/2.0/files/content":
                uploads.append(response.status_code)
                if response.ok:
                    self.files.extend(entry["id"] for entry in response.json()["entries"])
            return response

        with (
            patch.object(client.sessions, "start", side_effect=track_start),
            patch.object(demo, "NotteClient", return_value=client),
            patch.object(requests, "post", side_effect=track_upload),
            patch.dict(os.environ, BOX_FOLDER_ID=folder_id),
        ):
            try:
                yield uploads
            finally:
                self.assertEqual(len(ids), 1, "Expected one owned browser")
                for _ in range(30):
                    status = client.sessions.status(session_id=ids[0])
                    if status.status == "closed":
                        break
                    time.sleep(0.5)
                self.assertEqual(status.status, "closed", "Owned browser did not close")

    def test_original_demo_uploads_verified_capture(self):
        with self.owned(self.folder_id) as uploads:
            result = demo.main()
            self.assertIn(result["box_file_id"], self.files)
            self.assertEqual(uploads, [201])

    def test_real_box_failure_closes_browser(self):
        with self.owned("not-a-folder") as uploads:
            with self.assertRaisesRegex(RuntimeError, r"Box upload failed \(HTTP (400|404)\)"):
                demo.main()
            self.assertEqual(len(uploads), 1)
            self.assertIn(uploads[0], (400, 404))


if __name__ == "__main__":
    unittest.main()
