# @sniptest filename=check_run_status.py
# @sniptest show=12-15
import json
import os

from notte_sdk import NotteClient

client = NotteClient()
function = client.Function(os.environ["NOTTE_FUNCTION_ID"])

result = function.run(url="https://example.com")
run_id = result.function_run_id

run_status = function.get_run(run_id)

print(f"Status: {run_status.status}")  # "active", "closed", "failed"
print(f"Result: {run_status.result}")

print(json.dumps({"status": run_status.status, "same_run": run_status.function_run_id == result.function_run_id}))
