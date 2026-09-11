# @sniptest filename=check_run_status.py
# @sniptest show=8-13
from notte_sdk import NotteClient

client = NotteClient()
function = client.Function("function_abc123")
run_id = "run_xyz789"

# Check run status
run_status = function.get_run(run_id)

print(f"Status: {run_status.status}")  # "active", "closed", "failed"
print(f"Result: {run_status.result}")
