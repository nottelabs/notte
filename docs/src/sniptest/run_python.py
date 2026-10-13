"""Execute an unchanged example and report selected globals to the paired test runner."""

import json
import runpy
import sys


def capture_example(path: str) -> dict:
    namespace = runpy.run_path(path, run_name="__main__")
    fields = ("status", "title", "viewport", "session_id", "error_message", "result", "results", "run_status", "run_id")
    return {
        key: value.model_dump(mode="json") if hasattr(value, "model_dump") else value
        for key in fields
        if (value := namespace.get(key)) is not None
    }


if __name__ == "__main__":
    print(json.dumps(capture_example(sys.argv[1])))
