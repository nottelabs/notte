# @sniptest filename=cloud_execution.py
import json
import os

from notte_sdk import NotteClient

client = NotteClient()
function = client.Function(os.environ["NOTTE_FUNCTION_ID"])

# Run on Notte infrastructure (the default).
result = function.run(url="https://example.com", local=False)
print(json.dumps({"status": result.status, "result": result.result}))
