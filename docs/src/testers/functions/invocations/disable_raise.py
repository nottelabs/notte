# @sniptest filename=disable_raise.py
import json
import os

from notte_sdk import NotteClient

client = NotteClient()
function = client.Function(os.environ["NOTTE_FUNCTION_ID"])

# Inspect a failed run without raising an exception.
result = function.run(url="https://example.com", fail=True, raise_on_failure=False)
print(json.dumps({"status": result.status}))
