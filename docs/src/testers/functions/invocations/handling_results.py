# @sniptest filename=handling_results.py
import json
import os

from notte_sdk import NotteClient

client = NotteClient()
function = client.Function(os.environ["NOTTE_FUNCTION_ID"])

# Check the final status and structured return value.
result = function.run(url="https://example.com")
print(json.dumps({"status": result.status, "result": result.result}))
