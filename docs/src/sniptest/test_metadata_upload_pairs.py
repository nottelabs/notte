"""Keep metadata and URL-upload teaching blocks free of live-test scaffolding."""

import os
import runpy
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from parser import parse_file

ROOT = Path(__file__).resolve().parents[1] / "testers"


class MetadataUploadPairsTest(unittest.TestCase):
    def test_display_ranges_preserve_teaching_operations(self):
        for name, expected in (
            ("functions/management/get_function_details", ("Name:", "Description:", "Latest Version:", "Versions:")),
            ("functions/management/version_history", ("Function:", "Versions:", "Latest:")),
            ("file-storage/url_upload", ("upload_fixture.html", "upload_file", "text1.txt")),
        ):
            for suffix in ("py", "ts"):
                with self.subTest(name=name, language=suffix):
                    config, code = parse_file(ROOT / f"{name}.{suffix}")
                    self.assertIsNotNone(config.show)
                    for text in expected:
                        self.assertIn(text, code)
                    for hidden in (
                        "assert",
                        "NOTTE_FUNCTION_ID",
                        "results =",
                        "status =",
                        "originalExecute",
                        "finally",
                    ):
                        self.assertNotIn(hidden, code)

    def test_function_metadata_checks_reject_missing_or_invalid_owned_function(self):
        for name in ("get_function_details", "version_history"):
            for valid in (False, True):
                with self.subTest(name=name, valid=valid):
                    response = types.SimpleNamespace(
                        function_id="owned",
                        name="Fixture",
                        description="Test",
                        latest_version="v1",
                        versions=["v1"] if valid else [],
                    )
                    client = types.SimpleNamespace(
                        Function=lambda **kwargs: types.SimpleNamespace(function_id="owned", response=response),
                        functions=types.SimpleNamespace(list=lambda: types.SimpleNamespace(items=[response])),
                    )
                    sdk = types.ModuleType("notte_sdk")
                    sdk.NotteClient = lambda: client
                    with (
                        patch.dict("sys.modules", {"notte_sdk": sdk}),
                        patch.dict(os.environ, {"NOTTE_FUNCTION_ID": "owned"}),
                        patch("builtins.print"),
                    ):
                        source = str(ROOT / f"functions/management/{name}.py")
                        if valid:
                            self.assertEqual(runpy.run_path(source)["results"], [True, True])
                        else:
                            with self.assertRaises(AssertionError):
                                runpy.run_path(source)
