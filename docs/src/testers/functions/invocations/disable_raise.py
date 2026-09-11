# @sniptest filename=disable_raise.py
# @sniptest show=8-13
import os

from notte_sdk import NotteClient

client = NotteClient()
function = client.Function(os.environ["NOTTE_FUNCTION_ID"])

# Inspect a failed run without raising an exception.
result = function.run(url="https://example.com", fail=True, raise_on_failure=False)
if result.status == "failed":
    print(f"Function failed: {result.result}")
else:
    print(f"Success: {result.result}")
