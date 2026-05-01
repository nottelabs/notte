# @sniptest filename=check_run_status.py
# @sniptest show=6-12
from notte_sdk import NotteClient

client = NotteClient()
run_id = "run_xyz789"

# Check run status
run_status = client.functions.get_run("function_abc123", run_id)

print(f"Status: {run_status.status}")  # "active", "closed", "failed"
print(f"Result: {run_status.result}")
