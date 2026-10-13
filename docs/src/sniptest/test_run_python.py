import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, patch

from run_python import capture_example


class PythonExampleCaptureTest(unittest.TestCase):
    def test_cdp_error_example_handles_failure_and_captures_only_success(self):
        example = Path(__file__).resolve().parent.parent / "testers/sessions/cdp/playwright_cdp_error_handling.py"
        for connected in (True, False):
            with self.subTest(connected=connected):
                client = MagicMock()
                session = client.Session.return_value.__enter__.return_value
                session.status.return_value = SimpleNamespace(model_dump=lambda mode: {"status": "active"})
                playwright = MagicMock()
                connect = playwright.return_value.__enter__.return_value.chromium.connect_over_cdp
                connect.return_value.is_connected.return_value = True
                if not connected:
                    connect.side_effect = RuntimeError("connection refused")
                sdk_module = ModuleType("notte_sdk")
                sdk_module.NotteClient = MagicMock(return_value=client)
                playwright_module = ModuleType("playwright.sync_api")
                playwright_module.sync_playwright = playwright
                output = StringIO()
                with patch.dict("sys.modules", {"notte_sdk": sdk_module, "playwright.sync_api": playwright_module}):
                    with redirect_stdout(output):
                        result = capture_example(str(example))
                connect.assert_called_once_with(session.cdp_url.return_value)
                client.Session.return_value.__exit__.assert_called_once_with(None, None, None)
                if connected:
                    self.assertEqual(result, {"status": {"status": "active"}})
                    session.status.assert_called_once()
                else:
                    self.assertEqual(result, {})
                    session.status.assert_not_called()
                    self.assertIn("CDP connection failed: connection refused", output.getvalue())

    def test_executes_unchanged_source_and_ignores_non_result_objects(self):
        source = 'client = object()\nresult = {"status": "closed"}\ntitle = "Example Domain"\n'
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "example.py"
            path.write_text(source)
            self.assertEqual(capture_example(str(path)), {"result": {"status": "closed"}, "title": "Example Domain"})
            self.assertEqual(path.read_text(), source)

    def test_serializes_sdk_response_models_in_the_runner(self):
        source = 'class Response:\n    def model_dump(self, mode):\n        return {"status": "closed"}\nresult = Response()\n'
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "example.py"
            path.write_text(source)
            self.assertEqual(capture_example(str(path)), {"result": {"status": "closed"}})

    def test_example_errors_are_not_swallowed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "example.py"
            path.write_text('raise RuntimeError("example failed")\n')
            with self.assertRaisesRegex(RuntimeError, "example failed"):
                capture_example(str(path))


if __name__ == "__main__":
    unittest.main()
