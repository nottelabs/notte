import tempfile
import unittest
from pathlib import Path

from run_python import capture_example


class PythonExampleCaptureTest(unittest.TestCase):
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
