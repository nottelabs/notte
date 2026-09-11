# @sniptest filename=check_run_status.py
import json
import os

from notte_sdk import NotteClient

client = NotteClient()
function = client.Function(os.environ["NOTTE_FUNCTION_ID"])

result = function.run(url="https://example.com")
# Retrieve a run owned by this example, rather than a placeholder ID.
run_status = function.get_run(result.function_run_id)
print(json.dumps({"status": run_status.status, "same_run": run_status.function_run_id == result.function_run_id}))
