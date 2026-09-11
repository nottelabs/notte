"""Display regressions for file fixtures and function history examples."""

import runpy
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from parser import parse_file


class FunctionsFilesPairsTest(unittest.TestCase):
    def test_owned_fixture_setup_stays_out_of_documentation(self):
        root = Path(__file__).resolve().parents[1] / "testers"
        for name in (
            "file-storage/uploading_files",
            "file-storage/attach_before_starting",
            "functions/management/filter_active_runs",
            "file-storage/descriptive_filenames",
            "file-storage/force_overwrite",
            "functions/management/view_run_history",
        ):
            for suffix in (".py", ".ts"):
                with self.subTest(name=name, language=suffix):
                    config, rendered = parse_file(root / f"{name}{suffix}")
                    self.assertIsNotNone(config.show)
                    for hidden in ("assert", "export {", "NOTTE_FUNCTION_ID", "FixtureClient", "verified"):
                        self.assertNotIn(hidden, rendered)
                    if "view_run_history" in name:
                        for text in ("only_active", "Run ID:", "Created:", "Updated:"):
                            self.assertIn(text, rendered)
                    elif "force_overwrite" in name:
                        self.assertIn(".download(", rendered)
                        self.assertIn("force", rendered)
                    elif "filter_active" in name:
                        self.assertIn("only_active", rendered)
                        self.assertIn("Active runs:", rendered)
                    else:
                        self.assertIn(".upload(", rendered)
                        if suffix == ".py":
                            self.assertNotIn("status = session.status()", rendered)


class UploadCleanupTest(unittest.TestCase):
    def test_overwrite_failure_deletes_fixture_and_closes_session(self):
        deleted = []
        stopped = []

        class Storage:
            def upload(self, *args):
                return types.SimpleNamespace(id="owned-file")

            def download(self, *args, **kwargs):
                raise RuntimeError("download failed")

            def delete(self, file_id):
                deleted.append(file_id)

        class Session:
            storage = Storage()
            session_id = "owned-session"

            def __enter__(self):
                return self

            def __exit__(self, *args):
                stopped.append(True)

        sdk = types.ModuleType("notte_sdk")
        sdk.NotteClient = lambda: types.SimpleNamespace(Session=Session, FileStorage=lambda _: Session.storage)
        source = Path(__file__).resolve().parents[1] / "testers/file-storage/force_overwrite.py"
        with (
            patch.dict("sys.modules", {"notte_sdk": sdk}),
            patch.object(Path, "mkdir"),
            patch.object(Path, "write_bytes"),
        ):
            with self.assertRaisesRegex(RuntimeError, "download failed"):
                runpy.run_path(str(source))
        self.assertEqual(deleted, ["owned-file"])
        self.assertEqual(stopped, [True])

    def test_partial_failures_delete_all_successful_uploads(self):
        root = Path(__file__).resolve().parents[1] / "testers/file-storage"
        for example in ("uploading_files", "attach_before_starting", "descriptive_filenames"):
            failures = ["status", "list", "delete"]
            if example == "uploading_files":
                failures.append("second-upload")
            for failure in failures:
                with self.subTest(example=example, failure=failure):
                    self.check_failure(root / f"{example}.py", failure)

    def check_failure(self, source, failure):
        uploaded = []
        deleted = []
        stopped = []

        class Storage:
            def upload(self, *args, **kwargs):
                if failure == "second-upload" and uploaded:
                    raise RuntimeError("upload failed")
                item = types.SimpleNamespace(id=str(len(uploaded) + 1))
                uploaded.append(item)
                return item

            def list(self, **kwargs):
                if failure == "list":
                    raise RuntimeError("list failed")
                return types.SimpleNamespace(files=[])

            def delete(self, file_id):
                deleted.append(file_id)
                if failure == "delete" and file_id == "1":
                    raise RuntimeError("delete failed")

        class Session:
            storage = Storage()
            session_id = "owned-session"

            def __enter__(self):
                return self

            def __exit__(self, *args):
                stopped.append(True)

            def status(self):
                if failure != "list":
                    raise RuntimeError("status failed")
                return types.SimpleNamespace(status="active")

        sdk = types.ModuleType("notte_sdk")
        sdk.NotteClient = lambda: types.SimpleNamespace(
            Session=Session, sessions=types.SimpleNamespace(status=lambda _: None)
        )
        files = types.ModuleType("notte_sdk.endpoints.files")
        files.RemoteFileStorage = Storage
        original = Storage.upload
        with patch.dict("sys.modules", {"notte_sdk": sdk, "notte_sdk.endpoints.files": files}):
            with self.assertRaises(Exception), patch("builtins.print"):
                runpy.run_path(str(source))
        self.assertEqual(deleted, [file.id for file in uploaded])
        self.assertTrue(uploaded)
        self.assertEqual(stopped, [True])
        self.assertIs(Storage.upload, original)
