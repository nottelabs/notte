# @sniptest filename=stream_sdk.py
import json
import os

from notte_sdk import NotteClient

client = NotteClient()
function = client.Function(os.environ["NOTTE_FUNCTION_ID"])

# Stream logs while waiting for the final result.
result = function.run(url="https://example.com", stream=True)
print(json.dumps({"status": result.status, "result": result.result}))
