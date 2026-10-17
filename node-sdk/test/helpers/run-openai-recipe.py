"""Keep provider failures useful without exposing SDK connection details."""

import json
import os
import re
import runpy
import sys

runner, example = sys.argv[1:]
sys.argv = [runner, example]
try:
    _ = runpy.run_path(runner, run_name="__main__")
except Exception as error:
    cause = error.__context__ or error
    detail = f"{type(cause).__name__}: {cause}"
    for name, value in os.environ.items():
        if value and any(part in name.upper() for part in ("KEY", "TOKEN", "SECRET", "PASSWORD")):
            detail = detail.replace(value, "[REDACTED]")
    detail = re.sub(r"(?:wss?|https?)://[^\s\"'<>]+", "[URL]", detail)
    print("OPENAI_DIAGNOSTIC=" + json.dumps(detail[:1200]), file=sys.stderr)
    raise
