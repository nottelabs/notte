import hashlib
import json
import unittest
from types import SimpleNamespace

from main import upload_capture


class UploadTests(unittest.TestCase):
    def client(self, image, *, corrupt=False, fail=False):
        def response(value):
            return SimpleNamespace(raise_for_status=lambda: None, json=lambda: value)

        def post(url, **kwargs):
            self.assertEqual(url, "https://upload.box.com/api/2.0/files/content")
            if fail:
                raise RuntimeError("request headers contain test-only-token")
            self.assertEqual(json.loads(kwargs["data"]["attributes"])["parent"]["id"], "folder1")
            name, stream, content_type = kwargs["files"]["file"]
            self.assertEqual(name, "notte-session1.png")
            self.assertEqual(content_type, "image/png")
            self.assertEqual(stream.read(), image)
            return response({"entries": [{"id": "file1"}]})

        def get(url, **kwargs):
            self.assertEqual(url, "https://api.box.com/2.0/files/file1")
            self.assertEqual(kwargs["headers"]["Authorization"], "Bearer test-only-token")
            return response(
                {
                    "id": "file1",
                    "size": len(image),
                    "sha1": "wrong" if corrupt else hashlib.sha1(image, usedforsecurity=False).hexdigest(),
                }
            )

        return SimpleNamespace(post=post, get=get)

    def test_uploads_original_bytes_and_verifies_remote_content(self):
        image = b"offline-browser-capture"
        result = upload_capture(image, "session1", "test-only-token", "folder1", self.client(image))
        self.assertEqual(result, {"box_file_id": "file1", "session_id": "session1"})

    def test_rejects_mismatched_remote_content(self):
        image = b"offline-browser-capture"
        with self.assertRaisesRegex(RuntimeError, "Could not upload and verify"):
            upload_capture(image, "session1", "test-only-token", "folder1", self.client(image, corrupt=True))

    def test_provider_errors_do_not_expose_request_headers(self):
        with self.assertRaises(RuntimeError) as failure:
            upload_capture(b"test", "session1", "test-only-token", "folder1", self.client(b"test", fail=True))
        self.assertEqual(str(failure.exception), "Could not upload and verify the Box capture")


if __name__ == "__main__":
    unittest.main()
